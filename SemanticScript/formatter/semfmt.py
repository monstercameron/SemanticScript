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
    "htmlBody",
    "jsonBody",
})


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

    formatted = " ".join(token.raw for token in tokens)
    if inline_comment:
        formatted = f"{formatted}  {inline_comment}"
    return formatted


def split_preserving_physical_lines(source: str) -> List[str]:
    if source == "":
        return []
    return source.splitlines()


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
        head = formatted_line.split(" ", 1)[0]
        if head in INDENTED_ISLAND_VERBS:
            inside_indented_island = True

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
