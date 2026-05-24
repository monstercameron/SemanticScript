# Kilo SemanticScript Port

This directory contains a SemanticScript port of antirez/kilo. It now lives in
`experiments/` because it is a useful stress port, but not part of the curated
app demo set.

## Upstream

The upstream C implementation can be cloned locally, when parity comparison is
needed, at:

```text
experiments/kilo-port/upstream-kilo/
```

Clone origin:

```text
https://github.com/antirez/kilo.git
```

Current local baseline:

```text
323d93b29bd89a2cb446de90c4ed4fea1764176e
2025-01-04
Fix function declaration missing void.
```

`upstream-kilo/` is ignored and not required for normal build or smoke tests.
Port work lives in `build.sem`, `main.sem`, and generated artifacts under
`build/`.

## Layout

```text
experiments/kilo-port/
  README.md          # port notes and local commands
  parity.md          # upstream behavior checklist
  scripts/           # executable smoke tests
  upstream-kilo/     # optional ignored upstream C baseline
  build.sem          # SemanticScript project tape
  main.sem           # SemanticScript editor implementation
  build/             # generated executable and LLVM sidecars
```

The generic terminal runtime and compiler link plumbing live outside the app:

```text
SemanticScript/runtime/native_terminal/sem_terminal_runtime.c
SemanticScript/compiler/libc_registry.py
SemanticScript/compiler/semsc.py
```

The compiler only registers and links generic `terminal*` runtime symbols.
Kilo-specific editing behavior stays in `main.sem`.

## Build

Run from the repository root:

```powershell
cd C:\Users\Cam\Desktop\AgentScript
python SemanticScript\compiler\semsc.py experiments\kilo-port\build.sem --parse-only --lint --quiet
python SemanticScript\compiler\semsc.py experiments\kilo-port\build.sem --emit-exe --quiet
python experiments\kilo-port\scripts\test_kilo_port.py
```

The native executable is emitted as:

```text
experiments/kilo-port/build/kilo_port.exe
```

## Run

The port accepts a filename argument, matching the upstream `kilo <filename>`
workflow. If no argument is present, it falls back to `KILO_FILE`, then
`kilo.txt`.

```powershell
cd C:\Users\Cam\Desktop\AgentScript
.\experiments\kilo-port\build\kilo_port.exe scratch.txt
```

Fallback mode:

```powershell
$env:KILO_FILE = 'scratch.txt'
.\experiments\kilo-port\build\kilo_port.exe
```

## Key Bindings

- `Ctrl-S`: save
- `Ctrl-Q`: quit; dirty buffers require three warning presses, then the fourth
  `Ctrl-Q` exits
- `Ctrl-F`: search
- Arrow keys, `Home`, `End`, `Page Up`, `Page Down`: cursor/navigation
- `Enter`, `Backspace`, `Delete`, printable characters: editing

## Test Hook

The generic terminal runtime accepts scripted key bytes through
`SEM_TERMINAL_TEST_KEYS`. This is for automated executable smoke tests; normal
interactive runs do not set it.

## Port Notes

The port is a direct SemanticScript implementation of the editor loop, row
buffer, rendering, file load/save, editing operations, navigation, status bar,
and search prompt. It uses ANSI/VT100 output through `c.printf`/`c.putchar` and
keyboard/window/argv behavior through the generic native terminal runtime.

Remaining non-identical areas are tracked in `parity.md`, mainly full upstream
C/C++ syntax-highlighting depth and exact live-search overlay behavior.

## Upstream Comparison

Clone upstream first, then use this only to compare behavior against the
original C implementation:

```powershell
cd C:\Users\Cam\Desktop\AgentScript\experiments\kilo-port\upstream-kilo
make
.\kilo.exe scratch.txt
```
