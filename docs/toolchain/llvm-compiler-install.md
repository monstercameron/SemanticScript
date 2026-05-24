# LLVM Compiler Installation

SemanticScript can parse, check, format, inspect, and plan repairs with the
release `sem.exe` alone. Install LLVM/clang when you want native executable
output, native runtime linking, Windows resource embedding, or release parity
checks that exercise the `--emit-exe` path.

LLVM is a host toolchain dependency. It is not stored in this repository and is
not bundled into the main-channel `sem.exe` prerelease artifact.

## When You Need LLVM

Install LLVM/clang before running native AOT commands such as:

```powershell
sem build apps\taskforge-tui
sem doctor
```

`sem emit-ir` mainly depends on the compiler's embedded Python/llvmlite stack.
`sem build`, compiler `--emit-exe`, Windows icon/version resources, and native
runtime adapters require a discoverable C compiler. The supported default is
LLVM `clang`. `sem doctor` reports whether the current shell can find the
native backend tools.

## Windows

Recommended install options:

```powershell
winget install --id LLVM.LLVM -e
```

or install the official LLVM Windows package from
<https://github.com/llvm/llvm-project/releases>.

Add LLVM to the current shell if the installer did not update `PATH`:

```powershell
$env:Path = "C:\Program Files\LLVM\bin;$env:Path"
$env:SEMSC_CLANG = "C:\Program Files\LLVM\bin\clang.exe"
$env:SEMSC_WINRC = "C:\Program Files\LLVM\bin\llvm-rc.exe"
```

Persist those variables only after verifying the paths are correct for your
machine.

Verify:

```powershell
clang --version
llvm-rc --version
sem doctor
```

`SEMSC_CLANG` overrides the compiler used for executable linking. `SEMSC_WINRC`
overrides the Windows resource compiler used for embedded icon and VERSIONINFO
resources.

## macOS

Install the Homebrew LLVM package:

```bash
brew install llvm
```

Then expose the Homebrew LLVM binaries for the current shell. Apple Silicon
Homebrew usually uses `/opt/homebrew`; Intel Homebrew usually uses
`/usr/local`.

```bash
export PATH="/opt/homebrew/opt/llvm/bin:$PATH"
export SEMSC_CLANG="/opt/homebrew/opt/llvm/bin/clang"
```

Verify:

```bash
clang --version
sem doctor
```

Apple's system `clang` can compile simple programs, but Homebrew LLVM is the
preferred backend for repeatable SemanticScript native builds.

## Linux

Debian and Ubuntu:

```bash
sudo apt-get update
sudo apt-get install -y clang llvm lld build-essential
```

Fedora:

```bash
sudo dnf install -y clang llvm lld gcc
```

Arch:

```bash
sudo pacman -S --needed clang llvm lld base-devel
```

Verify:

```bash
clang --version
sem doctor
```

If multiple compiler versions are installed, point SemanticScript at the one you
want:

```bash
export SEMSC_CLANG=/usr/bin/clang
```

## Optional Native Runtime Libraries

Some experimental runtime paths need more than clang:

- Native async runtime: libuv, or CMake plus Git so the runtime build can fetch
  it.
- Outbound HTTP client runtime: libcurl, or CMake plus Git so the runtime build
  can fetch it.
- Native HTTP runtime checks: CMake plus clang or Zig.

Run `sem doctor` after installing LLVM. Optional runtime checks should either
pass or report the exact environment variables to set, such as `SEM_LIBUV_ROOT`,
`SEM_LIBUV_INCLUDE_DIR`, `SEM_LIBUV_LIB`, `SEM_CURL_ROOT`,
`SEM_CURL_INCLUDE_DIR`, and `SEM_CURL_LIB`.

## Troubleshooting

- If `sem doctor` reports `clang` as missing, confirm `clang --version` works in
  the same terminal where you run `sem`.
- If clang is installed but not on `PATH`, set `SEMSC_CLANG` to the full compiler
  path.
- If Windows resource embedding fails, set `SEMSC_WINRC` to `llvm-rc.exe`.
- If executable linking fails after LLVM is discovered, rerun with the same
  command in a developer shell and inspect the clang/linker diagnostic first.
