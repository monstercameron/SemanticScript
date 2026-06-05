from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parents[1]
DEFAULT_BUILD_ROOT = APP_ROOT / "build" / "real_async"
DEFAULT_API_ORIGIN = "http://127.0.0.1:18090"


def run_command(args: list[str], cwd: Path | None = None) -> None:
    printable = " ".join(str(arg) for arg in args)
    print(f"$ {printable}")
    subprocess.run(args, cwd=str(cwd) if cwd else None, check=True)


def find_clang() -> Path:
    env_clang = shutil.which("clang")
    candidates = [
        Path(sys.executable).parent / "clang.exe",
        Path("C:/Program Files/LLVM/bin/clang.exe"),
    ]
    if env_clang:
        candidates.insert(0, Path(env_clang))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise SystemExit("could not find clang; set SEMSC_CLANG or install LLVM clang")


def check_api_origin(api_origin: str) -> None:
    health_url = api_origin.rstrip("/") + "/health"
    try:
        with urlopen(health_url, timeout=5) as response:
            if response.status != 200:
                raise SystemExit(f"TaskForge health check returned HTTP {response.status}")
    except URLError as error:
        raise SystemExit(f"TaskForge server is not reachable at {health_url}: {error}") from error


def write_cmake_source(source_dir: Path, ir_path: Path, clang_path: Path) -> None:
    source_dir.mkdir(parents=True, exist_ok=True)
    runtime_dir = (REPO_ROOT / "SemanticScript" / "runtime" / "native_http_client").as_posix()
    cmake_text = f"""
    cmake_minimum_required(VERSION 3.20)
    project(taskforge_api_client_real C)

    add_subdirectory("{runtime_dir}" native_http_client)

    set(CLIENT_LL "{ir_path.as_posix()}")
    set(CLIENT_OBJ "${{CMAKE_CURRENT_BINARY_DIR}}/taskforge_api_client.obj")
    set(CLANG_EXE "{clang_path.as_posix()}")

    add_custom_command(
      OUTPUT "${{CLIENT_OBJ}}"
      COMMAND "${{CLANG_EXE}}" -c "${{CLIENT_LL}}" -o "${{CLIENT_OBJ}}"
      DEPENDS "${{CLIENT_LL}}"
      VERBATIM
    )

    add_executable(taskforge_api_client_real "${{CLIENT_OBJ}}")
    set_target_properties(taskforge_api_client_real PROPERTIES LINKER_LANGUAGE C)
    target_link_libraries(taskforge_api_client_real PRIVATE sem_http_client_runtime)
    """
    (source_dir / "CMakeLists.txt").write_text(textwrap.dedent(cmake_text).lstrip(), encoding="utf-8")


def real_exe_path(cmake_build_dir: Path, config: str) -> Path:
    windows_multi_config = cmake_build_dir / config / "taskforge_api_client_real.exe"
    if windows_multi_config.exists():
        return windows_multi_config
    return cmake_build_dir / "taskforge_api_client_real"


def build_real_client(
    build_root: Path,
    config: str,
    source_path: Path | None = None,
) -> Path:
    build_root.mkdir(parents=True, exist_ok=True)
    source_dir = build_root / "cmake-src"
    cmake_build_dir = build_root / "cmake-build"
    ir_path = build_root / "taskforge_api_client.ll"
    clang_path = find_clang()
    cmake = shutil.which("cmake")
    if not cmake:
        raise SystemExit("could not find cmake on PATH")
    if source_path is None:
        source_path = APP_ROOT / "main.sem"

    run_command([
        sys.executable,
        str(REPO_ROOT / "SemanticScript" / "compiler" / "semsc.py"),
        str(source_path),
        "--emit-ir",
        str(ir_path),
        "--quiet",
    ], cwd=REPO_ROOT)

    write_cmake_source(source_dir, ir_path, clang_path)

    run_command([
        cmake,
        "-S",
        str(source_dir),
        "-B",
        str(cmake_build_dir),
        "-DSEM_ASYNC_WITH_LIBUV=ON",
        "-DSEM_HTTP_CLIENT_WITH_CURL=ON",
        f"-DCMAKE_BUILD_TYPE={config}",
    ])
    run_command([
        cmake,
        "--build",
        str(cmake_build_dir),
        "--config",
        config,
        "--target",
        "taskforge_api_client_real",
    ])
    exe = real_exe_path(cmake_build_dir, config)
    if not exe.exists():
        raise SystemExit(f"real async client executable was not produced at {exe}")
    return exe


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the TaskForge SemanticScript API client with real libuv/libcurl runtime support."
    )
    parser.add_argument("--build-root", default=str(DEFAULT_BUILD_ROOT))
    parser.add_argument("--config", default="Release")
    parser.add_argument("--api-origin", default=DEFAULT_API_ORIGIN)
    parser.add_argument(
        "--source",
        default=str(APP_ROOT / "main.sem"),
        help="SemanticScript source file to compile; defaults to this app's main.sem",
    )
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args(argv)

    exe = build_real_client(Path(args.build_root), args.config, Path(args.source))
    print(f"built real async client: {exe}")

    if args.run:
        check_api_origin(args.api_origin)
        completed = subprocess.run([str(exe)], cwd=str(REPO_ROOT), text=True)
        return completed.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
