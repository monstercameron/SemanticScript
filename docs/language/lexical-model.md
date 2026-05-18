# Lexical Model

The reference tokenizer is `tokenize_line` in `AgentScript/compiler/ascc.py`.
It is intentionally small and predictable.

## Tokenization

For each physical line:

1. Trim leading and trailing whitespace.
2. Skip empty lines.
3. If the trimmed line starts with `#`, produce a comment token.
4. Otherwise split on whitespace, except quoted strings stay one token.

Quoted strings use double quotes:

```agentscript
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

```agentscript
arg addCall left leftValue
arg addCall right rightValue
```

There is no `add(leftValue, rightValue)` form.

## Comments

Plain comments are ignored by codegen:

```agentscript
# This is normal commentary.
```

Typed semantic comments are preserved by the parser and attached to the current
operation when an operation is active:

```agentscript
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

```agentscript
# group consoleOutput
call writeGreetingCall console.writeLine
arg writeGreetingCall text greetingText
run writeGreetingCall
# endGroup consoleOutput
```

## Identifier Shape

AgentScript uses naming as source data:

```text
camelCaseName            values, operations, call objects, labels
PascalCaseName           types, records, enums, errors
dot.path.name            dependency paths and call targets
ERROR.VARIANT            typed error variant reference
```

Underscore-heavy names are avoided in AgentScript source. The C registry exposes
camelCase aliases for C symbols that contain underscores, such as
`c.alignedAlloc` for `aligned_alloc`.

## Rejected Source Forms

These are intentionally not AgentScript syntax:

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

```agentscript
call sumCall math.addI64
arg sumCall left invoiceSubtotal
arg sumCall right taxAmount
run sumCall
bind invoiceTotal I64 sumCall
```

