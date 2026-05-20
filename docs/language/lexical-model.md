# Lexical Model

The reference tokenizer is `tokenize_line` in `SemanticScript/compiler/semsc.py`.
It is intentionally small and predictable.

## Tokenization

For each physical line:

1. Trim leading and trailing whitespace.
2. Skip empty lines.
3. If the trimmed line starts with `#`, produce a comment token.
4. Otherwise split on whitespace, except quoted strings stay one token.

Quoted strings use double quotes:

```semanticscript
const greetingText String "hello world"
purpose main "Print a greeting with one exact line"
```

Supported escapes inside strings:

| Escape | Value |
|---|---|
| `\n` | newline |
| `\t` | tab |
| `\r` | carriage return |
| `\\` | backslash |
| `\"` | double quote |
| `\0` | null byte |

The tokenizer does not parse expressions. Every unquoted token is an atom:

```semanticscript
arg addCall left leftValue
arg addCall right rightValue
```

There is no `add(leftValue, rightValue)` form.

## Grammar Islands

SemanticScript normally rejects indentation blocks, brace blocks, and generic
angle-bracket syntax because executable source is a row tape. `htmlBody` and
`jsonBody` are narrow exceptions: a column-0 row starts an indented literal
island, and the island ends at the next non-empty column-0 SemanticScript row.

The exception exists only for data formats whose native syntax would be damaged
by row tokenization. HTML/SSX keeps tags, attributes, and `{htmlArg.name}` holes
inside `htmlBody`; JSON keeps braces, brackets, strings, and commas inside
`jsonBody`. Those islands must be attached to explicit declaration rows such as
`htmlTemplate` / `htmlArg` or `storage ... JsonText`, so the compiler and linter
still see typed boundaries around the non-row text.

## Language Modes

Language mode rows are normal top-level rows:

```semanticscript
languageMode strictExecutable
languageMode refinedSyntax
```

`strictExecutable` closes the executable grammar from that point in the resolved
source stream. Unknown lowercase top-level and operation-body verbs become parse
errors. Plain comments, typed semantic comments, and `# group` / `# endGroup`
anchors remain parseable because they are comments, not executable rows.

`refinedSyntax` keeps permissive parsing for research files and metadata-heavy
examples that intentionally use proposed lowercase rows. Do not use it to hide
misspelled executable rows in production source.

## Comments

Plain comments are ignored by codegen:

```semanticscript
# This is normal commentary.
```

Typed semantic comments are preserved by the parser and attached to the current
operation when an operation is active:

```semanticscript
# rationale: this branch preserves the external API's exit-code contract
# invariant: output remains a single newline-terminated line
# warning: changing the format string changes benchmark parity
```

Recognized typed comment prefixes:

```text
rationale invariant warning agent memory concurrency timing failure
security dependency observability test todo
```

Group anchors are also preserved:

```semanticscript
# group consoleOutput
call writeGreetingCall console.writeLine
arg writeGreetingCall text greetingText
run writeGreetingCall
# endGroup consoleOutput
```

## Identifier Shape

SemanticScript uses naming as source data:

```text
camelCaseName            values, operations, call objects, labels
PascalCaseName           types, records, enums, errors
dot.path.name            dependency paths and call targets
ERROR.VARIANT            typed error variant reference
```

Underscore-heavy names are avoided in SemanticScript source. The C registry exposes
camelCase aliases for C symbols that contain underscores, such as
`c.alignedAlloc` for `aligned_alloc`.

## Rejected Source Forms

These are intentionally not SemanticScript syntax:

```text
infix operators
semicolon statement separators
brace blocks
indentation blocks
parenthesized call expressions
comma argument lists
generic angle brackets
implicit current call objects
exceptions
implicit async
dynamic object literals
dynamic array literals
```

Use explicit line records instead:

```semanticscript
call sumCall math.addI64
arg sumCall left invoiceSubtotal
arg sumCall right taxAmount
run sumCall
bind invoiceTotal I64 sumCall
```
