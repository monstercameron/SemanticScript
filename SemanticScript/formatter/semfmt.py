#!/usr/bin/env python3
"""Conservative formatter for SemanticScript source rows.

The formatter intentionally works at the physical-row layer. SemanticScript
source is a flat semantic tape, so v1 only normalizes things that are safe for
that model:

* one space between code tokens;
* string literal spellings preserved byte-for-byte;
* trailing whitespace removed;
* full-line comments preserved, with optional cleanup for accidental
  ``# # rationale:`` style typed-comment headings;
* inline comments separated from code by two spaces;
* blank-line runs collapsed to one separator line.
"""

from __future__ import annotations

import argparse
import difflib
import glob
import io
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, TextIO, Tuple

__version__ = "0.1.0"

SUPPORTED_SUFFIXES = frozenset({".sem", ".sscript"})
DEFAULT_EXCLUDED_DIRECTORIES = frozenset({
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    "build",
    "dist",
    "third_party",
})

TYPED_COMMENT_PREFIXES = frozenset({
    "rationale",
    "invariant",
    "warning",
    "agent",
    "memory",
    "concurrency",
    "timing",
    "failure",
    "security",
    "dependency",
    "observability",
    "test",
    "todo",
})

INDENTED_ISLAND_VERBS = frozenset({
    "jsonBody",
})

REPLACED_ROW_VERBS = frozenset({
    "arg",
    "bindOk",
    "bindError",
    "branchIf",
    "branchIfError",
    "const",
    "ignoreValue",
    "ignoreOk",
    "ignoreError",
    "importModule",
    "let",
    "memoryHeap",
    "modulePurpose",
    "moduleInvariant",
    "htmlTemplate",
    "htmlArg",
    "htmlBody",
    "returnValue",
    "returnOk",
    "returnError",
    "returnVoid",
    "var",
})

METADATA_SUBJECT_KINDS = frozenset({"module", "operation"})
SIGNATURE_SUBJECT_KINDS = frozenset({"operation"})
BIND_VARIANTS = frozenset({"value", "ok", "error"})
BRANCH_VARIANTS = frozenset({"if", "error", "else"})
RETURN_VARIANTS = frozenset({"value", "ok", "error", "void"})
IGNORE_VARIANTS = frozenset({"value", "ok", "error", "void"})


class FormatError(ValueError):
    """Raised when the formatter cannot safely tokenize a source line."""


@dataclass(frozen=True)
class Token:
    raw: str
    start: int
    end: int
    kind: str


def detect_newline(source: str) -> str:
    crlf_index = source.find("\r\n")
    lf_index = source.find("\n")
    if crlf_index != -1 and (lf_index == -1 or crlf_index <= lf_index):
        return "\r\n"
    if lf_index != -1:
        return "\n"
    return "\n"


def _is_nested_typed_comment(body: str) -> Optional[str]:
    stripped = body.lstrip()
    if not stripped.startswith("#"):
        return None
    nested = stripped[1:].lstrip()
    head, separator, _ = nested.partition(":")
    if separator != ":":
        return None
    if head.strip() not in TYPED_COMMENT_PREFIXES:
        return None
    return nested


def format_full_line_comment(line: str, *, normalize_comment_headings: bool = True) -> str:
    hash_index = line.find("#")
    body = line[hash_index + 1:].rstrip()
    if not body:
        return "#"

    if normalize_comment_headings:
        nested = _is_nested_typed_comment(body)
        if nested is not None:
            return f"# {nested}"

    return "#" + body


def tokenize_code_prefix(line: str) -> Tuple[List[Token], Optional[str]]:
    tokens: List[Token] = []
    index = 0
    length = len(line)
    inline_comment: Optional[str] = None

    while index < length:
        char = line[index]
        if char.isspace():
            index += 1
            continue
        if char == "#":
            inline_comment = line[index:].rstrip()
            break
        if char == '"':
            start = index
            index += 1
            while index < length:
                current = line[index]
                if current == "\\" and index + 1 < length:
                    index += 2
                    continue
                if current == '"':
                    index += 1
                    break
                index += 1
            else:
                raise FormatError(f"unterminated string literal: {line!r}")
            tokens.append(Token(line[start:index], start, index, "string"))
            continue

        start = index
        while index < length and not line[index].isspace() and line[index] != "#":
            index += 1
        tokens.append(Token(line[start:index], start, index, "atom"))

    return tokens, inline_comment


def _token_values(tokens: Sequence[Token]) -> List[str]:
    return [token.raw for token in tokens]


def _raise_replaced_syntax(row: str, *, reason: str) -> None:
    raise FormatError(f"{reason}: {row!r}")


def reject_replaced_syntax(tokens: Sequence[Token], row: str) -> None:
    """Reject rows the cutover says normal formatting must not emit."""

    if not tokens:
        return

    values = _token_values(tokens)
    head = values[0]

    if head in REPLACED_ROW_VERBS:
        _raise_replaced_syntax(row, reason=f"replaced SemanticScript row verb {head!r}")

    if head.startswith("@") or head.startswith("#"):
        _raise_replaced_syntax(row, reason=f"forbidden row prefix in {head!r}")

    if "." in head:
        _raise_replaced_syntax(row, reason=f"forbidden dotted row verb {head!r}")

    if any(token.kind == "atom" and "=" in token.raw for token in tokens):
        _raise_replaced_syntax(row, reason="forbidden equals-sign row shape")

    if head == "type" and len(values) >= 3 and values[2] == "Result":
        _raise_replaced_syntax(row, reason="replaced result type row")

    if head in {"purpose", "invariant"} and len(values) >= 2:
        if values[1] not in METADATA_SUBJECT_KINDS:
            _raise_replaced_syntax(row, reason=f"bare {head} row is replaced")

    if head in {"input", "output"} and len(values) >= 2:
        if values[1] not in SIGNATURE_SUBJECT_KINDS:
            _raise_replaced_syntax(row, reason=f"subject kind is required for {head} row")

    if head == "set" and len(values) >= 2 and values[1] in {"local", "module"}:
        _raise_replaced_syntax(row, reason=f"replaced set target {values[1]!r}")

    if head == "bind" and (len(values) < 2 or values[1] not in BIND_VARIANTS):
        _raise_replaced_syntax(row, reason="bind row must use value/ok/error variant")

    if head == "branch" and (len(values) < 2 or values[1] not in BRANCH_VARIANTS):
        _raise_replaced_syntax(row, reason="branch row must use if/error/else variant")

    if head == "return" and (len(values) < 2 or values[1] not in RETURN_VARIANTS):
        _raise_replaced_syntax(row, reason="return row must use value/ok/error/void variant")

    if head == "ignore" and (len(values) < 2 or values[1] not in IGNORE_VARIANTS):
        _raise_replaced_syntax(row, reason="ignore row must use value/ok/error/void variant")

    if values[:2] == ["ignore", "value"] and len(values) >= 6:
        for index, value in enumerate(values[:-1]):
            if value == "type" and values[index + 1] == "Void":
                _raise_replaced_syntax(row, reason="void calls must use ignore void")

    if head == "html":
        valid_html = (
            values[:2] == ["html", "template"] and len(values) == 3
        ) or (
            values[:3] == ["html", "body", "template"] and len(values) == 4
        )
        if not valid_html:
            _raise_replaced_syntax(
                row,
                reason="html row must use template or body template shape",
            )


def format_line(line: str, *, normalize_comment_headings: bool = True) -> str:
    trimmed_right = line.rstrip()
    if not trimmed_right.strip():
        return ""

    first_non_space = len(trimmed_right) - len(trimmed_right.lstrip())
    if trimmed_right[first_non_space] == "#":
        return format_full_line_comment(
            trimmed_right,
            normalize_comment_headings=normalize_comment_headings,
        )

    tokens, inline_comment = tokenize_code_prefix(trimmed_right)
    if not tokens:
        return inline_comment or ""

    reject_replaced_syntax(tokens, trimmed_right)

    formatted = " ".join(token.raw for token in tokens)
    if inline_comment:
        formatted = f"{formatted}  {inline_comment}"
    return formatted


def split_preserving_physical_lines(source: str) -> List[str]:
    if source == "":
        return []
    return source.splitlines()


def _is_blank_or_full_line_comment(line: str) -> bool:
    return line == "" or line.lstrip().startswith("#")


def _formatted_code_tokens(line: str) -> List[str]:
    if _is_blank_or_full_line_comment(line):
        return []
    tokens, _ = tokenize_code_prefix(line)
    return _token_values(tokens)


def _is_branch_with_attached_else(line: str) -> bool:
    tokens = _formatted_code_tokens(line)
    return len(tokens) >= 2 and tokens[0] == "branch" and tokens[1] in {"if", "error"}


def _is_branch_else(line: str) -> bool:
    tokens = _formatted_code_tokens(line)
    return len(tokens) >= 2 and tokens[0] == "branch" and tokens[1] == "else"


def _is_indented_island_start(line: str) -> bool:
    tokens = _formatted_code_tokens(line)
    return (
        bool(tokens) and tokens[0] in INDENTED_ISLAND_VERBS
    ) or tokens[:3] == ["html", "body", "template"]


def preserve_branch_pair_adjacency(lines: Sequence[str]) -> List[str]:
    """Move blank/comment separators out from between attached branch pairs."""

    output_lines: List[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not _is_branch_with_attached_else(line):
            output_lines.append(line)
            index += 1
            continue

        pending_separators: List[str] = []
        lookahead = index + 1
        while lookahead < len(lines) and _is_blank_or_full_line_comment(lines[lookahead]):
            pending_separators.append(lines[lookahead])
            lookahead += 1

        if (
            pending_separators
            and lookahead < len(lines)
            and _is_branch_else(lines[lookahead])
        ):
            output_lines.append(line)
            output_lines.append(lines[lookahead])
            output_lines.extend(pending_separators)
            index = lookahead + 1
            continue

        output_lines.append(line)
        index += 1

    return output_lines


def collapse_blank_runs(lines: Sequence[str], *, max_blank_lines: int) -> List[str]:
    output_lines: List[str] = []
    blank_run = 0
    for line in lines:
        if line == "":
            blank_run += 1
            if output_lines and blank_run <= max_blank_lines:
                output_lines.append(line)
            continue
        blank_run = 0
        output_lines.append(line)
    return output_lines


def format_source(
    source: str,
    *,
    normalize_comment_headings: bool = True,
    max_blank_lines: int = 1,
    final_newline: bool = True,
) -> str:
    newline = detect_newline(source)
    output_lines: List[str] = []
    blank_run = 0
    inside_indented_island = False

    for line in split_preserving_physical_lines(source):
        if inside_indented_island:
            if not line.strip():
                output_lines.append("")
                continue
            if line.startswith((" ", "\t")):
                output_lines.append(line.rstrip())
                continue
            inside_indented_island = False

        formatted_line = format_line(
            line,
            normalize_comment_headings=normalize_comment_headings,
        )
        if formatted_line == "":
            blank_run += 1
            if output_lines and blank_run <= max_blank_lines:
                output_lines.append("")
            continue
        blank_run = 0
        output_lines.append(formatted_line)
        if _is_indented_island_start(formatted_line):
            inside_indented_island = True

    output_lines = preserve_branch_pair_adjacency(output_lines)
    output_lines = collapse_blank_runs(output_lines, max_blank_lines=max_blank_lines)

    while output_lines and output_lines[-1] == "":
        output_lines.pop()

    if not output_lines:
        return newline if final_newline and source else ""

    formatted = newline.join(output_lines)
    if final_newline:
        formatted += newline
    return formatted


def _iter_source_files(directory: Path) -> Iterable[Path]:
    for root, dirs, files in os.walk(directory):
        dirs[:] = [
            dirname for dirname in dirs
            if dirname not in DEFAULT_EXCLUDED_DIRECTORIES
        ]
        for filename in files:
            path = Path(root) / filename
            if path.suffix in SUPPORTED_SUFFIXES:
                yield path


def collect_paths(paths: Sequence[str]) -> List[Path]:
    collected: List[Path] = []
    seen = set()

    for raw_path in paths:
        matches: List[Path]
        if any(character in raw_path for character in "*?["):
            matches = [Path(match) for match in glob.glob(raw_path, recursive=True)]
        else:
            matches = [Path(raw_path)]

        for match in matches:
            if match.is_dir():
                candidates = sorted(_iter_source_files(match))
            else:
                candidates = [match]
            for candidate in candidates:
                if candidate.suffix not in SUPPORTED_SUFFIXES:
                    continue
                resolved = candidate.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                collected.append(candidate)

    return collected


def diff_text(original: str, formatted: str, *, path_label: str) -> str:
    original_lines = original.splitlines(keepends=True)
    formatted_lines = formatted.splitlines(keepends=True)
    return "".join(difflib.unified_diff(
        original_lines,
        formatted_lines,
        fromfile=path_label,
        tofile=f"{path_label} (formatted)",
    ))


def format_file(
    path: Path,
    *,
    check: bool = False,
    diff: bool = False,
    write: bool = True,
    stdout: TextIO = sys.stdout,
    normalize_comment_headings: bool = True,
) -> bool:
    original = path.read_text(encoding="utf-8")
    formatted = format_source(
        original,
        normalize_comment_headings=normalize_comment_headings,
    )
    changed = original != formatted

    if changed and diff:
        stdout.write(diff_text(original, formatted, path_label=str(path)))

    if changed and write and not check and not diff:
        path.write_text(formatted, encoding="utf-8", newline="")

    return changed


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="semfmt",
        description="Format SemanticScript .sem and .sscript source files.",
        epilog=(
            "examples:\n"
            "  semfmt app/todo/main.sscript\n"
            "  semfmt --check SemanticScript/tests/tiny.sem\n"
            "  semfmt --diff \"app/**/*.sem\"\n"
            "  semfmt --stdin-file-name scratch.sem < scratch.sem"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("paths", nargs="*", help="Files, directories, or glob patterns to format.")
    parser.add_argument("--version", action="version", version=f"semfmt {__version__}")
    parser.add_argument("--check", action="store_true", help="Exit non-zero when formatting drift is found.")
    parser.add_argument("--diff", action="store_true", help="Print unified diffs instead of writing files.")
    parser.add_argument(
        "--stdin-file-name",
        help="Read source from stdin and use this path for diagnostics/editor integration.",
    )
    parser.add_argument(
        "--no-normalize-comment-headings",
        action="store_true",
        help="Preserve accidental nested typed-comment headings such as '# # rationale:'.",
    )
    return parser


def _run_stdin_mode(
    *,
    stdin_file_name: str,
    check: bool,
    diff: bool,
    stdin: TextIO,
    stdout: TextIO,
    stderr: TextIO,
    normalize_comment_headings: bool,
) -> int:
    original = stdin.read()
    formatted = format_source(
        original,
        normalize_comment_headings=normalize_comment_headings,
    )
    changed = original != formatted
    if diff:
        stdout.write(diff_text(original, formatted, path_label=stdin_file_name))
    elif not check:
        stdout.write(formatted)
    if check and changed:
        stderr.write(f"would reformat {stdin_file_name}\n")
        return 1
    return 0


def run(
    argv: Optional[Sequence[str]] = None,
    *,
    stdin: TextIO = sys.stdin,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    normalize_comment_headings = not args.no_normalize_comment_headings

    if args.stdin_file_name:
        return _run_stdin_mode(
            stdin_file_name=args.stdin_file_name,
            check=args.check,
            diff=args.diff,
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
            normalize_comment_headings=normalize_comment_headings,
        )

    if not args.paths:
        parser.error("provide at least one path or --stdin-file-name")

    paths = collect_paths(args.paths)
    if not paths:
        stderr.write("semfmt: no .sem or .sscript files matched\n")
        return 2

    changed_paths: List[Path] = []
    for path in paths:
        try:
            changed = format_file(
                path,
                check=args.check,
                diff=args.diff,
                write=True,
                stdout=stdout,
                normalize_comment_headings=normalize_comment_headings,
            )
        except OSError as exc:
            stderr.write(f"semfmt: {path}: {exc}\n")
            return 2
        except FormatError as exc:
            stderr.write(f"semfmt: {path}: {exc}\n")
            return 2

        if changed:
            changed_paths.append(path)

    if args.check and changed_paths:
        for path in changed_paths:
            stderr.write(f"would reformat {path}\n")
        return 1

    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
