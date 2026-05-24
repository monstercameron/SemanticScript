import os
import pathlib
import subprocess
import tempfile


ROOT = pathlib.Path(__file__).resolve().parents[3]
EXE = ROOT / "experiments" / "kilo-port" / "build" / "kilo_port.exe"


def run_editor(keys, args=(), extra_env=None, timeout=5):
    env = os.environ.copy()
    env["SEM_TERMINAL_TEST_KEYS"] = keys
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [str(EXE), *map(str, args)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        timeout=timeout,
    )


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    require(EXE.exists(), f"missing executable: {EXE}")
    ctrl_s = chr(19)
    ctrl_q = chr(17)
    ctrl_f = chr(6)
    enter = chr(13)
    arrow_right = chr(224) + chr(77)
    page_down = chr(224) + chr(81)

    with tempfile.TemporaryDirectory(prefix="kilo-port-") as temp_dir:
        temp = pathlib.Path(temp_dir)

        argv_file = temp / "argv-save.txt"
        proc = run_editor("abc" + ctrl_s + ctrl_q, args=[argv_file])
        require(proc.returncode == 0, "argv save run failed")
        require(argv_file.read_text(encoding="utf-8") == "abc\n", "argv save content mismatch")

        long_line_file = temp / "long-line.txt"
        long_line = "x" * 300
        proc = run_editor(long_line + ctrl_s + ctrl_q, args=[long_line_file])
        require(proc.returncode == 0, "long line save run failed")
        require(long_line_file.read_text(encoding="utf-8") == long_line + "\n", "long line content mismatch")

        tab_file = temp / "tab-save.txt"
        proc = run_editor("a\tb" + ctrl_s + ctrl_q, args=[tab_file])
        require(proc.returncode == 0, "tab save run failed")
        require(tab_file.read_text(encoding="utf-8") == "a\tb\n", "tab save content mismatch")
        require(b"a      " in proc.stdout, "tab did not render to the expected Kilo spacing")

        js_file = temp / "sample.js"
        js_file.write_text(
            "const answer = 42;\n// comment\nfunction go() { return true; }\n",
            encoding="utf-8",
        )
        proc = run_editor(ctrl_q, args=[js_file])
        require(proc.returncode == 0, "javascript highlight render run failed")
        require(b"\x1b[33m" in proc.stdout, "javascript keyword color missing")
        require(b"\x1b[32m" in proc.stdout, "javascript literal/type color missing")
        require(b"\x1b[36m" in proc.stdout, "javascript comment color missing")
        require(b"\x1b[31m" in proc.stdout, "javascript number color missing")

        search_file = temp / "search.txt"
        search_file.write_text("first\nalpha\nsecond alpha\n", encoding="utf-8")
        proc = run_editor(ctrl_f + "alpha" + arrow_right + enter + ctrl_q, args=[search_file])
        require(proc.returncode == 0, "live search render run failed")
        require(b"\x1b[34m" in proc.stdout, "search match color missing")

        page_file = temp / "page.txt"
        page_file.write_text("\n".join(f"line {index:02d}" for index in range(40)) + "\n", encoding="utf-8")
        proc = run_editor(page_down + ctrl_q, args=[page_file])
        require(proc.returncode == 0, "page down run failed")

        env_file = temp / "env-save.txt"
        proc = run_editor("xy" + ctrl_s + ctrl_q, extra_env={"KILO_FILE": str(env_file)})
        require(proc.returncode == 0, "KILO_FILE save run failed")
        require(env_file.read_text(encoding="utf-8") == "xy\n", "KILO_FILE save content mismatch")

        argv_precedence_file = temp / "argv-precedence.txt"
        env_precedence_file = temp / "env-should-not-be-used.txt"
        proc = run_editor(
            "p" + ctrl_s + ctrl_q,
            args=[argv_precedence_file],
            extra_env={"KILO_FILE": str(env_precedence_file)},
        )
        require(proc.returncode == 0, "argv precedence run failed")
        require(argv_precedence_file.read_text(encoding="utf-8") == "p\n", "argv precedence content mismatch")
        require(not env_precedence_file.exists(), "KILO_FILE unexpectedly used when argv was present")

        dirty_file = temp / "dirty-quit.txt"
        try:
            run_editor("z" + (ctrl_q * 3), args=[dirty_file], timeout=2)
        except subprocess.TimeoutExpired:
            pass
        else:
            raise AssertionError("dirty buffer exited before the fourth Ctrl-Q")

        proc = run_editor("z" + (ctrl_q * 4), args=[dirty_file], timeout=5)
        require(proc.returncode == 0, "dirty fourth Ctrl-Q run failed")
        require(not dirty_file.exists(), "dirty quit unexpectedly saved a file")

    print("kilo_port smoke tests passed")


if __name__ == "__main__":
    main()
