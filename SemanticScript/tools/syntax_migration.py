#!/usr/bin/env python3
"""One-shot SemanticScript old-to-new syntax converter.

This module is deliberately separate from the parser. It rewrites legacy source
text for migration review and reports rows that need manual context.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path


ACTIONS = {
    "read", "write", "append", "delete", "execute", "open", "close", "create",
    "update", "observe", "allocate", "free", "send", "receive", "connect",
    "configure",
}


@dataclass
class Issue:
    line: int
    message: str
    text: str


@dataclass
class MigrationResult:
    text: str
    issues: list[Issue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


@dataclass
class Context:
    current_operation: str | None = None
    current_module: str | None = None
    import_aliases: dict[str, str] = field(default_factory=dict)
    call_targets: dict[str, str] = field(default_factory=dict)
    op_inputs: dict[tuple[str, str], str] = field(default_factory=dict)
    value_types: dict[str, str] = field(default_factory=dict)


BUILTIN_ARGUMENT_TYPES: dict[tuple[str, str], str] = {
    ("gui.windowCreate", "layout"): "GuiWindowLayout",
    ("gui.listBoxCreate", "selectionMode"): "GuiListBoxSelectionMode",
    ("gui.controlOnEvent", "eventKind"): "GuiEventKind",
    ("gui.controlOnEvent", "handler"): "GuiEventHandler",
    ("http.responseText", "contentType"): "HttpContentType",
    ("sqlite.openDatabase", "mode"): "SqliteOpenMode",
    ("sqlite.exec", "sql"): "String",
    ("bcrypt.hashPassword", "cost"): "Int32",
    ("math.equalInt32", "right"): "Int32",
    ("math.equalInt64", "right"): "Int64",
}


def split_code_comment(line: str) -> tuple[str, str]:
    in_quote = False
    escaped = False
    for index, char in enumerate(line):
        if escaped:
            escaped = False
            continue
        if char == "\\" and in_quote:
            escaped = True
            continue
        if char == '"':
            in_quote = not in_quote
            continue
        if char == "#" and not in_quote:
            if index == 0 or line[index - 1].isspace():
                return line[:index].rstrip(), line[index:]
    return line.rstrip(), ""


def tokenize_code(code: str) -> list[str]:
    tokens: list[str] = []
    token: list[str] = []
    in_quote = False
    escaped = False
    for char in code.strip().splitlines()[0] if code.strip() else "":
        if escaped:
            token.append(char)
            escaped = False
            continue
        if char == "\\" and in_quote:
            token.append(char)
            escaped = True
            continue
        if char == '"':
            token.append(char)
            in_quote = not in_quote
            continue
        if char.isspace() and not in_quote:
            if token:
                tokens.append("".join(token))
                token = []
            continue
        token.append(char)
    if token:
        tokens.append("".join(token))
    return tokens


def line_prefix(line: str) -> str:
    return line[:len(line) - len(line.lstrip(" \t"))]


def join_row(prefix: str, tokens: list[str], comment: str) -> str:
    row = prefix + " ".join(tokens)
    if comment:
        row += "  " + comment
    return row


def collect_context(source: str) -> Context:
    ctx = Context()
    for raw in source.splitlines():
        code, _comment = split_code_comment(raw)
        tokens = tokenize_code(code)
        if not tokens:
            continue
        verb = tokens[0]
        if verb == "module" and len(tokens) >= 2:
            ctx.current_module = tokens[1]
        elif verb in {"import", "importModule"}:
            parsed = _parse_import_row(tokens)
            if parsed:
                alias, module_path = parsed
                ctx.import_aliases.setdefault(alias, module_path)
        elif verb == "operation" and len(tokens) >= 2:
            ctx.current_operation = tokens[1]
        elif verb == "input":
            if len(tokens) >= 4:
                if tokens[1] == "operation" and len(tokens) >= 5:
                    _record_operation_input(ctx, tokens[2], tokens[3], tokens[4])
                    _record_value_type(ctx, tokens[3], tokens[4])
                else:
                    _record_operation_input(ctx, tokens[1], tokens[2], tokens[3])
                    _record_value_type(ctx, tokens[2], tokens[3])
        elif verb == "htmlArg" and len(tokens) >= 4:
            _record_operation_input(ctx, f"html.hydrate.{tokens[1]}", tokens[2], tokens[3])
        elif (verb == "html" and len(tokens) >= 6
              and tokens[1] == "parameter" and tokens[2] == "template"):
            _record_operation_input(ctx, f"html.hydrate.{tokens[3]}", tokens[4], tokens[5])
        elif verb in {"output", "async", "effect", "authority", "purpose", "invariant"}:
            continue
        elif verb == "call" and len(tokens) >= 3:
            ctx.call_targets[tokens[1]] = tokens[2]
        elif verb in {"storage", "memory"}:
            _collect_new_storage_or_memory(ctx, tokens)
        elif verb in {"const", "let", "var"} and len(tokens) >= 3:
            _record_value_type(ctx, tokens[1], tokens[2])
        elif verb == "buildConstant" and len(tokens) >= 4:
            _record_value_type(ctx, tokens[2], tokens[3])
        elif verb in {"domainLiteral", "enumCase", "literal"} and len(tokens) >= 3:
            if verb == "enumCase":
                _record_value_type(ctx, tokens[2], tokens[1])
            else:
                _record_value_type(ctx, tokens[1], tokens[2])
        elif verb == "bind" and len(tokens) >= 4:
            if tokens[1] in {"value", "ok", "error"} and len(tokens) >= 5:
                _record_value_type(ctx, tokens[2], tokens[3])
            else:
                _record_value_type(ctx, tokens[1], tokens[2])
        elif verb in {"bindOk", "bindError"} and len(tokens) >= 3:
            _record_value_type(ctx, tokens[1], tokens[2])
    return ctx


def _collect_new_storage_or_memory(ctx: Context, tokens: list[str]) -> None:
    if tokens[0] == "storage" and len(tokens) >= 5:
        _record_value_type(ctx, tokens[3], tokens[4])
    elif tokens[0] == "memory" and len(tokens) >= 6 and tokens[2] in {"mutable", "immutable"}:
        _record_value_type(ctx, tokens[3], tokens[4])


def _record_operation_input(ctx: Context, operation: str, parameter: str, type_name: str) -> None:
    ctx.op_inputs.setdefault((operation, parameter), type_name)
    if ctx.current_module:
        ctx.op_inputs.setdefault((f"{ctx.current_module}.{operation}", parameter), type_name)


def _record_value_type(ctx: Context, value_name: str, type_name: str) -> None:
    ctx.value_types.setdefault(value_name, type_name)
    if ctx.current_module:
        ctx.value_types.setdefault(f"{ctx.current_module}.{value_name}", type_name)


def _parse_import_row(tokens: list[str]) -> tuple[str, str] | None:
    if not tokens:
        return None
    if tokens[0] == "import":
        if len(tokens) == 3:
            return tokens[1], tokens[2]
        return None
    if tokens[0] == "importModule":
        if len(tokens) >= 4 and tokens[2] == "as":
            return tokens[3], tokens[1]
        if len(tokens) == 3:
            return tokens[1], tokens[2]
        if len(tokens) == 2:
            module_path = tokens[1]
            return module_path.rsplit(".", 1)[-1], module_path
    return None


def merge_contexts(global_context: Context | None, local_context: Context) -> Context:
    if global_context is None:
        return local_context
    merged = Context(
        current_operation=local_context.current_operation,
        current_module=local_context.current_module,
        import_aliases=dict(local_context.import_aliases),
        call_targets=dict(local_context.call_targets),
        op_inputs=dict(global_context.op_inputs),
        value_types=dict(global_context.value_types),
    )
    merged.op_inputs.update(local_context.op_inputs)
    merged.value_types.update(local_context.value_types)
    return merged


def collect_combined_context(sources: list[str]) -> Context:
    combined = Context()
    for source in sources:
        ctx = collect_context(source)
        combined.op_inputs.update(ctx.op_inputs)
        combined.value_types.update(ctx.value_types)
    return combined


def migrate_text(source: str, *, global_context: Context | None = None) -> MigrationResult:
    ctx = merge_contexts(global_context, collect_context(source))
    issues: list[Issue] = []
    out: list[str] = []
    pending_branch = False
    queued_between_branch: list[str] = []
    current_operation: str | None = None

    def flush_pending() -> None:
        nonlocal pending_branch, queued_between_branch
        out.extend(queued_between_branch)
        queued_between_branch = []
        pending_branch = False

    for line_no, raw in enumerate(source.splitlines(), start=1):
        raw = re.sub(r"\{\s*(?:htmlArg|parameter)\.([A-Za-z_][A-Za-z0-9_]*)\s*\}", r"{\1}", raw)
        raw = re.sub(r"\b(?:HtmlText|HtmlClass|SafeUrl)\b", "String", raw)
        code, comment = split_code_comment(raw)
        tokens = tokenize_code(code)
        prefix = line_prefix(raw)

        if not tokens:
            if pending_branch:
                queued_between_branch.append(raw)
            else:
                out.append(raw)
            continue

        verb = tokens[0]
        if pending_branch:
            if verb == "branch" and len(tokens) == 2:
                out.append(join_row(prefix, ["branch", "else", "target", tokens[1]], comment))
                out.extend(queued_between_branch)
                queued_between_branch = []
                pending_branch = False
                continue
            flush_pending()

        replacement: list[str] | None = None
        keep_pending = False

        if verb == "operation" and len(tokens) >= 2:
            current_operation = tokens[1]
        elif verb == "importModule":
            parsed_import = _parse_import_row(tokens)
            if parsed_import:
                alias, module_path = parsed_import
                replacement = ["import", alias, module_path]
            else:
                issues.append(Issue(line_no, "`importModule` row cannot be converted", raw))
        elif verb == "htmlTemplate" and len(tokens) == 2:
            replacement = ["html", "template", tokens[1]]
        elif verb == "htmlArg" and len(tokens) == 4:
            replacement = []
        elif (verb == "html" and len(tokens) == 6
              and tokens[1] == "parameter" and tokens[2] == "template"):
            replacement = []
        elif verb == "htmlBody" and len(tokens) == 2:
            replacement = ["html", "body", "template", tokens[1]]
        elif verb == "type" and len(tokens) == 5 and tokens[2] == "Result":
            replacement = ["type", tokens[1], "result", "ok", tokens[3], "error", tokens[4]]
        elif verb == "modulePurpose" and len(tokens) >= 3:
            replacement = ["purpose", "module", tokens[1], *tokens[2:]]
        elif verb == "moduleInvariant" and len(tokens) >= 3:
            replacement = ["invariant", "module", tokens[1], *tokens[2:]]
        elif verb in {"purpose", "invariant"} and len(tokens) >= 3 and tokens[1] not in {"module", "operation"}:
            replacement = [verb, "operation", tokens[1], *tokens[2:]]
        elif verb == "input" and len(tokens) == 4 and tokens[1] != "operation":
            replacement = ["input", "operation", tokens[1], tokens[2], tokens[3]]
        elif verb == "output":
            if len(tokens) == 3:
                replacement = ["output", "operation", tokens[1], tokens[2]]
            elif len(tokens) == 5 and tokens[2] == "Result":
                replacement = ["output", "operation", tokens[1], "Result", tokens[3], tokens[4]]
        elif verb == "const" and len(tokens) >= 4:
            replacement = ["storage", "module", "immutable", tokens[1], tokens[2], *tokens[3:]]
        elif verb in {"var", "let"} and len(tokens) >= 4:
            if current_operation:
                replacement = ["memory", current_operation, "mutable", tokens[1], tokens[2], *tokens[3:]]
            else:
                issues.append(Issue(line_no, f"`{verb}` requires an enclosing operation to convert to memory", raw))
        elif verb == "memoryHeap" and len(tokens) >= 3:
            replacement = ["memory", tokens[1], "heap", *tokens[2:]]
        elif verb == "authority" and len(tokens) == 4 and _looks_like_old_authority(tokens):
            replacement = ["authority", tokens[1], tokens[3], tokens[2]]
        elif verb == "set" and len(tokens) >= 4 and tokens[1] == "local":
            replacement = ["set", "memory", *tokens[2:]]
        elif verb == "set" and len(tokens) >= 4 and tokens[1] == "module":
            replacement = ["set", "storage", *tokens[2:]]
        elif verb == "set" and len(tokens) == 3:
            replacement = ["set", "memory", tokens[1], tokens[2]]
        elif verb == "bind" and len(tokens) == 4 and tokens[1] not in {"value", "ok", "error"}:
            replacement = ["bind", "value", tokens[1], tokens[2], tokens[3]]
        elif verb == "bindOk" and len(tokens) == 4:
            replacement = ["bind", "ok", tokens[1], tokens[2], tokens[3]]
        elif verb == "bindError" and len(tokens) == 4:
            replacement = ["bind", "error", tokens[1], tokens[2], tokens[3]]
        elif verb == "arg" and len(tokens) == 4:
            inferred = infer_argument_type(ctx, tokens[1], tokens[2], tokens[3])
            if inferred:
                replacement = ["argument", tokens[1], tokens[2], inferred, tokens[3]]
            else:
                issues.append(Issue(line_no, "cannot infer argument type from call signature or value declaration", raw))
        elif verb == "branchIf":
            if len(tokens) == 3:
                replacement = ["branch", "if", "condition", tokens[1], "target", tokens[2]]
                keep_pending = True
            elif len(tokens) == 4:
                out.append(join_row(prefix, ["branch", "if", "condition", tokens[1], "target", tokens[2]], comment))
                out.append(join_row(prefix, ["branch", "else", "target", tokens[3]], ""))
                continue
        elif verb == "branchIfError" and len(tokens) == 3:
            replacement = ["branch", "error", "source", tokens[1], "target", tokens[2]]
            keep_pending = True
        elif verb == "branch" and len(tokens) == 2:
            replacement = ["jump", "target", tokens[1]]
        elif verb == "returnValue" and len(tokens) >= 2:
            replacement = ["return", "value", *tokens[1:]]
        elif verb == "returnOk" and len(tokens) >= 2:
            replacement = ["return", "ok", *tokens[1:]]
        elif verb == "returnError" and len(tokens) >= 2:
            replacement = ["return", "error", *tokens[1:]]
        elif verb == "returnVoid" and len(tokens) == 1:
            replacement = ["return", "void"]
        elif verb == "ignoreValue" and len(tokens) == 3:
            if tokens[2] == "Void":
                replacement = ["ignore", "void", "source", tokens[1]]
            else:
                replacement = ["ignore", "value", "source", tokens[1], "type", tokens[2]]
        elif verb == "ignoreOk" and len(tokens) == 3:
            if tokens[2] in {"Void", "Void"}:
                replacement = ["ignore", "void", "source", tokens[1]]
            else:
                replacement = ["ignore", "ok", "source", tokens[1], "type", tokens[2]]
        elif verb == "ignoreError" and len(tokens) == 2:
            replacement = ["ignore", "error", "source", tokens[1]]
        elif (verb == "ignore" and len(tokens) == 6 and tokens[1] == "ok"
              and tokens[2] == "source" and tokens[4] == "type"
              and tokens[5] in {"Void", "Void"}):
            replacement = ["ignore", "void", "source", tokens[3]]

        if replacement is None:
            out.append(raw)
        elif replacement == []:
            pending_branch = keep_pending
        else:
            out.append(join_row(prefix, replacement, comment))
            pending_branch = keep_pending

    if pending_branch:
        out.extend(queued_between_branch)
    trailing_newline = "\n" if source.endswith(("\n", "\r\n")) else ""
    return MigrationResult("\n".join(out) + trailing_newline, issues)


def infer_argument_type(ctx: Context, call_name: str, arg_name: str, value_name: str) -> str | None:
    target = ctx.call_targets.get(call_name)
    if target:
        for candidate in _target_candidates(ctx, target):
            declared = ctx.op_inputs.get((candidate, arg_name))
            if declared:
                return declared
            declared = BUILTIN_ARGUMENT_TYPES.get((candidate, arg_name))
            if declared:
                return declared
    for candidate in _value_candidates(ctx, value_name):
        declared = ctx.value_types.get(candidate)
        if declared:
            return declared
    return None


def _target_candidates(ctx: Context, target: str) -> list[str]:
    candidates = [target]
    if "." in target:
        alias, suffix = target.split(".", 1)
        module_path = ctx.import_aliases.get(alias)
        if module_path:
            candidates.append(f"{module_path}.{suffix}")
        candidates.append(target.rsplit(".", 1)[-1])
    return _dedupe(candidates)


def _value_candidates(ctx: Context, value_name: str) -> list[str]:
    candidates = [value_name]
    if "." in value_name:
        alias, suffix = value_name.split(".", 1)
        module_path = ctx.import_aliases.get(alias)
        if module_path:
            candidates.append(f"{module_path}.{suffix}")
        candidates.append(value_name.rsplit(".", 1)[-1])
    return _dedupe(candidates)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _looks_like_old_authority(tokens: list[str]) -> bool:
    if len(tokens) != 4 or tokens[0] != "authority":
        return False
    _verb, _operation, third, fourth = tokens
    if third in ACTIONS:
        return False
    return fourth in ACTIONS or ("." in third and "." not in fourth)


def unified_diff(path: Path, before: str, after: str) -> str:
    return "".join(difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=str(path),
        tofile=str(path),
    ))


def migrate_file(path: Path, *, write: bool = False,
                 global_context: Context | None = None) -> MigrationResult:
    before = path.read_text(encoding="utf-8")
    result = migrate_text(before, global_context=global_context)
    if write and result.text != before:
        path.write_text(result.text, encoding="utf-8", newline="\n")
    return result


def _paths_from_args(paths: list[str]) -> list[Path]:
    resolved: list[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            resolved.extend(sorted(
                p for p in path.rglob("*")
                if p.suffix in {".sem", ".sscript"} and p.is_file()
            ))
        else:
            resolved.append(path)
    return resolved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Convert legacy SemanticScript syntax explicitly.")
    parser.add_argument("--write", action="store_true", help="rewrite files in place")
    parser.add_argument("--diff", action="store_true", help="print unified diffs")
    parser.add_argument("--json", action="store_true", help="emit machine-readable results")
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args(argv)

    sources_by_path = {
        path: path.read_text(encoding="utf-8")
        for path in _paths_from_args(args.paths)
    }
    global_context = collect_combined_context(list(sources_by_path.values()))
    payload = []
    exit_code = 0
    for path, before in sources_by_path.items():
        result = migrate_text(before, global_context=global_context)
        changed = result.text != before
        if args.diff and changed:
            print(unified_diff(path, before, result.text), end="")
        if args.write and changed:
            path.write_text(result.text, encoding="utf-8", newline="\n")
        if result.issues:
            exit_code = 1
        payload.append({
            "path": str(path),
            "changed": changed,
            "issues": [issue.__dict__ for issue in result.issues],
        })
    if args.json:
        print(json.dumps({"files": payload}, indent=2))
    elif not args.diff:
        for item in payload:
            status = "changed" if item["changed"] else "unchanged"
            print(f"{status}: {item['path']}")
            for issue in item["issues"]:
                print(f"  line {issue['line']}: {issue['message']}: {issue['text']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
