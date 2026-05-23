from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SERVER = ROOT / "experiments" / "realtime-auction-arena" / "server"
RUNTIME = ROOT / "SemanticScript" / "runtime" / "native_http"
COMPILER = ROOT / "SemanticScript" / "compiler" / "semsc.py"
STD_HTTP = ROOT / "SemanticScript" / "std" / "http" / "main.sem"
SERVER_CONTEXT = SERVER / "src" / "server_context.sem"
WIRE_ENVELOPES = SERVER / "src" / "wire_envelopes.sem"
HTTP_HELPERS = SERVER / "src" / "http_helpers.sem"
SSE_CONTEXT = SERVER / "src" / "sse_context.sem"


def read(path):
    return path.read_text(encoding="utf-8")


def assert_contains(text, needle, label):
    assert needle in text, f"missing {label}: {needle}"


def assert_not_contains(text, needle, label):
    assert needle not in text, f"unexpected {label}: {needle}"


def test_sse_stream_primitives_are_stdlib_owned():
    runtime = read(RUNTIME / "sem_http_runtime.c")
    header = read(RUNTIME / "sem_http_runtime.h")
    compiler = read(COMPILER)
    std_http = read(STD_HTTP)

    assert_contains(runtime, "int ss_http_response_sse_event", "one-shot SSE formatter")
    assert_contains(runtime, '"Content-Length: %zu\\r\\n"', "fixed response length")
    assert_contains(runtime, '"Connection: close\\r\\n"', "closed one-shot response")
    assert_not_contains(runtime, "Transfer-Encoding: chunked", "chunked streaming transport")
    assert_contains(runtime, "int ss_http_sse_open", "streaming SSE C ABI")
    assert_contains(runtime, "int ss_http_sse_write_event", "streaming SSE write ABI")
    assert_contains(runtime, "int ss_http_sse_write_event_with_id", "streaming SSE id write ABI")
    assert_contains(runtime, "int ss_http_sse_heartbeat", "streaming SSE heartbeat ABI")
    assert_not_contains(compiler, 'target == "http.sseOpen"', "streaming SSE compiler target")
    assert_not_contains(compiler, 'target == "http.sseWriteEventWithId"', "streaming SSE id compiler target")
    assert_contains(std_http, "runtimeBinding openSseStreamNative native.ss_http_sse_open", "stdlib SSE open binding")
    assert_contains(std_http, "runtimeBinding writeSseEventWithIdNative native.ss_http_sse_write_event_with_id", "stdlib SSE id binding")
    assert_contains(std_http, "exportOperation standard.http openSseStream", "stdlib SSE export")
    assert_contains(std_http, "exportOperation standard.http writeSseEventWithId", "stdlib SSE id export")
    assert_contains(header, "standard.http owns the SSE stream API surface", "header ownership warning")


def test_native_http_accept_loop_has_process_signal_shutdown_only():
    runtime = read(RUNTIME / "sem_http_runtime.c")
    header = read(RUNTIME / "sem_http_runtime.h")
    std_http = read(STD_HTTP)
    server_context = read(SERVER_CONTEXT)
    wire = read(WIRE_ENVELOPES)
    helpers = read(HTTP_HELPERS)

    for needle in [
        "SS_HTTP_SHUTDOWN_POLL_MILLIS 250",
        "request_http_shutdown_from_signal",
        "int ss_http_server_is_shutting_down(void)",
        "SIGINT",
        "SIGTERM",
        "wait_for_listen_socket",
        "while (!http_shutdown_requested())",
        "free_compiled_routes();",
        "return SS_HTTP_OK;",
    ]:
        assert_contains(runtime, needle, "native shutdown support")

    assert_contains(header, "process-level graceful shutdown only", "shutdown scope")
    assert_contains(header, "standard.http exposes the", "shutdown stdlib scope")
    assert_contains(header, "request cancellation", "cancellation scope")
    assert_contains(std_http, "exportOperation standard.http serverIsShuttingDown", "stdlib shutdown export")
    assert_contains(std_http, "runtimeBinding serverIsShuttingDownNative native.ss_http_server_is_shutting_down", "stdlib shutdown binding")
    assert_contains(std_http, "nativeRuntimeSource standard.http", "stdlib native runtime metadata")
    assert_contains(server_context, "call readyShutdownCall http.serverIsShuttingDown", "ready drain hook")
    assert_contains(server_context, "call requestContextShutdownCall http.serverIsShuttingDown", "middleware drain hook")
    assert_contains(server_context, "return value shortCircuitMiddlewareControl", "middleware shutdown short circuit")
    assert_contains(wire, "server_shutting_down", "shutdown envelope code")
    assert_contains(helpers, "writeServerShuttingDownEnvelope", "shutdown envelope helper")


def test_server_docs_describe_executable_sse_replay_without_overclaiming_live_fanout():
    api = read(SERVER / "docs" / "api-contract.md")
    gaps = read(SERVER / "docs" / "runtime-gaps.md")
    todo = read(SERVER / "TODO.md")
    sse_context = read(SSE_CONTEXT)

    assert_contains(api, "returns bounded JSON replay by default", "api contract")
    assert_contains(api, "Accept: text/event-stream", "api contract")
    assert_contains(api, "`writeSseEventWithId`", "api contract stdlib primitive")
    assert_contains(api, "streaming replay transport, not a multi-client live subscription yet", "api contract")
    assert_contains(gaps, "bounded JSON replay by default", "runtime gaps")
    assert_contains(gaps, "opt-in SSE replay frames", "runtime gaps")
    assert_contains(gaps, "Long-lived live SSE fanout still needs", "runtime gaps")
    assert_contains(api, "standard.http", "api contract")
    assert_contains(gaps, "blocking SSE stream primitives", "runtime gaps")
    assert_contains(gaps, "one-shot", "runtime gaps")
    assert_contains(gaps, "frame formatter", "runtime gaps")
    assert_contains(sse_context, "call writeSseEventCall http.writeSseEventWithId", "SSE id frames")
    assert_contains(sse_context, "call writeSseHeartbeatCall http.writeSseHeartbeat", "SSE heartbeat")
    assert_contains(sse_context, "call clientDisconnectedCall http.clientDisconnected", "SSE disconnect check")

    assert_contains(gaps, "handler-observable drain state are", "shutdown docs")
    assert_contains(api, "standard.http.serverIsShuttingDown", "source-level shutdown docs")
    assert_contains(todo, "opt-in `Accept: text/event-stream` SSE replay", "SSE TODO precision")
    assert_contains(todo, "true long-lived live", "SSE TODO precision")
    assert_contains(todo, "fanout subscription", "SSE TODO precision")
    assert_contains(todo, "`http.writeSseEventWithId`", "SSE TODO precision")
    assert_contains(todo, "SemanticScript-visible shutdown drain-state hook", "shutdown TODO precision")
    assert_contains(todo, "request cancellation tokens", "cancellation TODO precision")


def main():
    test_sse_stream_primitives_are_stdlib_owned()
    test_native_http_accept_loop_has_process_signal_shutdown_only()
    test_server_docs_describe_executable_sse_replay_without_overclaiming_live_fanout()
    print("SSE/shutdown contract tests passed")


if __name__ == "__main__":
    main()
