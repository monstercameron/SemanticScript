from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SERVER = ROOT / "experiments" / "realtime-auction-arena" / "server"
RUNTIME = ROOT / "SemanticScript" / "runtime" / "native_http"
COMPILER = ROOT / "SemanticScript" / "compiler" / "semsc.py"
STD_HTTP = ROOT / "SemanticScript" / "std" / "http" / "main.sem"


def read(path):
    return path.read_text(encoding="utf-8")


def assert_contains(text, needle, label):
    assert needle in text, f"missing {label}: {needle}"


def assert_not_contains(text, needle, label):
    assert needle not in text, f"unexpected {label}: {needle}"


def test_native_http_adapter_still_has_only_one_shot_sse():
    runtime = read(RUNTIME / "sem_http_runtime.c")
    header = read(RUNTIME / "sem_http_runtime.h")
    compiler = read(COMPILER)
    std_http = read(STD_HTTP)

    assert_contains(runtime, "int ss_http_response_sse_event", "one-shot SSE formatter")
    assert_contains(runtime, '"Content-Length: %zu\\r\\n"', "fixed response length")
    assert_contains(runtime, '"Connection: close\\r\\n"', "closed one-shot response")
    assert_not_contains(runtime, "Transfer-Encoding: chunked", "chunked streaming transport")
    assert_not_contains(runtime, "ss_http_sse_open", "streaming SSE C ABI")
    assert_not_contains(compiler, "http.sseOpen", "streaming SSE compiler target")
    assert_not_contains(std_http, "httpSseStreamWriter", "streaming SSE std capability")
    assert_contains(header, "does not make long-lived streaming responses executable", "header warning")


def test_native_http_accept_loop_has_process_signal_shutdown_only():
    runtime = read(RUNTIME / "sem_http_runtime.c")
    header = read(RUNTIME / "sem_http_runtime.h")

    for needle in [
        "SS_HTTP_SHUTDOWN_POLL_MILLIS 250",
        "request_http_shutdown_from_signal",
        "SIGINT",
        "SIGTERM",
        "wait_for_listen_socket",
        "while (!http_shutdown_requested())",
        "free_compiled_routes();",
        "return SS_HTTP_OK;",
    ]:
        assert_contains(runtime, needle, "native shutdown support")

    assert_contains(header, "process-level graceful shutdown only", "shutdown scope")
    assert_contains(header, "SemanticScript cancellation token", "cancellation scope")
    assert_contains(header, "does not interrupt an in-flight handler", "handler drain scope")


def test_server_docs_do_not_overclaim_live_sse_or_source_level_cancellation():
    api = read(SERVER / "docs" / "api-contract.md")
    gaps = read(SERVER / "docs" / "runtime-gaps.md")
    todo = read(SERVER / "TODO.md")

    assert_contains(api, "currently returns JSON, not", "api contract")
    assert_contains(gaps, "bounded JSON replay", "runtime gaps")
    for text, label in [(api, "api contract"), (gaps, "runtime gaps")]:
        assert_contains(text, "Content-Length", label)
        assert_contains(text, "Connection: close", label)
        assert_contains(text, "one-shot", label)

    assert_contains(gaps, "process-signal accept-loop shutdown is executable", "shutdown docs")
    assert_contains(api, "Handler-observable drain state", "source-level cancellation docs")
    assert_contains(todo, "one-shot `http.responseSseEvent`", "SSE TODO precision")
    assert_contains(todo, "SemanticScript-visible shutdown/cancellation hooks", "shutdown TODO precision")


def main():
    test_native_http_adapter_still_has_only_one_shot_sse()
    test_native_http_accept_loop_has_process_signal_shutdown_only()
    test_server_docs_do_not_overclaim_live_sse_or_source_level_cancellation()
    print("SSE/shutdown contract tests passed")


if __name__ == "__main__":
    main()
