"""
fuzz_parser.py - parser/front-end never-crash fuzzer.

Feeds deterministically-mutated source at `semsc --parse-only` and asserts the
front end never falls over with a Python traceback. The compiler is allowed to
*reject* garbage (clean diagnostic, non-zero exit); it is not allowed to crash.

Two mutators run against a corpus of real valid sources:
  - **byte** mutations (flip/insert/delete/truncate raw bytes, including invalid
    UTF-8) exercise the file-read + lexer boundary; and
  - **structural** mutations (drop/duplicate/garble whole lines and tokens,
    while staying valid UTF-8) exercise parser logic on malformed-but-decodable
    programs.

This is build-free (no C compiler) so it runs in the component / ci-fast lane.
It is deterministic: the same SEM_FUZZ_SEED + SEM_FUZZ_ITERS always produces the
same inputs, so a CI failure reproduces exactly. Crank iterations up locally for
deeper runs:

    SEM_FUZZ_ITERS=5000 python SemanticScript/tests/fuzz_parser.py

History: this harness found two real robustness bugs on first run - an
unhandled UnicodeDecodeError on non-UTF-8 source, and a SyntaxError escaping
build-tape sniffing on an unterminated string literal (both since fixed).
"""

from __future__ import annotations

import os
import random
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SEMSC = ROOT / "compiler" / "semsc.py"

SEED = int(os.environ.get("SEM_FUZZ_SEED", "0xC0FFEE"), 0)
ITERS = int(os.environ.get("SEM_FUZZ_ITERS", "140"))
PARSE_TIMEOUT = 30

# Tokens used by structural mutation to splice plausible-but-wrong fragments.
TOKENS = [
    "operation", "storage", "module", "immutable", "call", "run", "bind",
    "argument", "branch", "return ok", "return error", "Int64", "Float64",
    "main", "purpose", "math.addInt64", "{", "}", "(", ")", ":", "-",
    "99999999999999999999", '"unterminated', '""', "\t", "  ",
]


def load_corpus() -> list[str]:
    paths = sorted((ROOT / "sem" / "feature_tests").glob("*.sscript"))
    paths += sorted((ROOT / "sem").glob("*.sscript"))
    corpus = []
    for path in paths:
        try:
            corpus.append(path.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            pass
    return corpus


def mutate_bytes(text: str, rng: random.Random) -> bytes:
    data = bytearray(text.encode("utf-8", "ignore"))
    if not data:
        return bytes(data)
    for _ in range(rng.randint(1, 8)):
        if not data:
            break
        i = rng.randrange(len(data))
        op = rng.randint(0, 4)
        if op == 0:
            data[i] = rng.randint(0, 255)            # flip to arbitrary byte
        elif op == 1:
            del data[i:i + rng.randint(1, 12)]        # delete a run
        elif op == 2:
            data[i:i] = bytes([rng.randint(0, 255)])  # insert arbitrary byte
        elif op == 3:
            data[i:i] = b"\x00\xff{}()[]\""           # insert nasty bytes
        else:
            data = data[:rng.randrange(len(data) + 1)]  # truncate
    return bytes(data)


def mutate_structure(text: str, rng: random.Random) -> bytes:
    lines = text.split("\n")
    for _ in range(rng.randint(1, 10)):
        if not lines:
            break
        i = rng.randrange(len(lines))
        op = rng.randint(0, 5)
        if op == 0:
            del lines[i]
        elif op == 1:
            lines[i:i] = [rng.choice(TOKENS)]
        elif op == 2:
            lines[i] = lines[i][:rng.randrange(len(lines[i]) + 1)]
        elif op == 3:
            lines[i] = lines[i] + " " + rng.choice(TOKENS)
        elif op == 4:
            lines[i] = rng.choice(TOKENS) * rng.randint(1, 5)
        else:
            lines[i] = lines[i] + lines[i]  # duplicate
    return "\n".join(lines).encode("utf-8")


def main() -> int:
    corpus = load_corpus()
    if not corpus:
        print("[ERR ] no fuzz corpus found")
        return 1

    rng = random.Random(SEED)
    failures: list[tuple[int, str, bytes]] = []
    print(f"fuzzing semsc --parse-only: {ITERS} iters, seed={hex(SEED)}, "
          f"corpus={len(corpus)} files")

    with tempfile.TemporaryDirectory(prefix="ss_fuzz_") as temp_dir:
        scratch = Path(temp_dir) / "case.sscript"
        for n in range(ITERS):
            base = rng.choice(corpus)
            data = mutate_bytes(base, rng) if n % 2 == 0 else mutate_structure(base, rng)
            scratch.write_bytes(data)
            try:
                proc = subprocess.run(
                    [sys.executable, str(SEMSC), str(scratch), "--parse-only"],
                    capture_output=True, text=True, timeout=PARSE_TIMEOUT,
                )
            except subprocess.TimeoutExpired:
                failures.append((n, "TIMEOUT", data))
                continue
            combined = proc.stdout + proc.stderr
            crashed = "Traceback (most recent call last)" in combined
            bad_rc = proc.returncode not in (0, 1, 2, 3)
            if crashed or bad_rc:
                why = "traceback" if crashed else f"exit={proc.returncode}"
                last = next((ln for ln in reversed(combined.splitlines()) if ln.strip()), "")
                failures.append((n, f"{why}: {last[:140]}", data))

    if failures:
        repro_dir = HERE / "fuzz_failures"
        repro_dir.mkdir(exist_ok=True)
        print(f"\n{len(failures)} crash(es) found (saving repros to {repro_dir}):")
        for n, why, data in failures[:20]:
            repro = repro_dir / f"crash_{SEED:x}_{n}.sscript"
            repro.write_bytes(data)
            print(f"  iter#{n}: {why}  -> {repro.name}")
        return 1

    print(f"\nNo crashes: front end rejected all {ITERS} mutations cleanly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
