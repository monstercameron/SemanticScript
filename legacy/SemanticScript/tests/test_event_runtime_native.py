import os
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
EVENT_RUNTIME = REPO_ROOT / "SemanticScript" / "std" / "event" / "native" / "sem_event_runtime.c"
ASYNC_RUNTIME = REPO_ROOT / "SemanticScript" / "runtime" / "native_async" / "sem_async_runtime.c"


def c_compiler_command() -> list[str] | None:
    configured = os.environ.get("SEMSC_CLANG")
    if configured:
        return configured.split()
    clang = shutil.which("clang")
    if clang:
        return [clang]
    zig = shutil.which("zig")
    if zig:
        return [zig, "cc"]
    return None


def compile_and_run(source: str) -> subprocess.CompletedProcess:
    cc = c_compiler_command()
    if cc is None:
        raise unittest.SkipTest("no clang or zig compiler available")
    with tempfile.TemporaryDirectory(prefix="ss_event_native_") as temp_dir:
        temp_path = Path(temp_dir)
        source_path = temp_path / "event_runtime_harness.c"
        exe_path = temp_path / ("event_runtime_harness.exe" if os.name == "nt" else "event_runtime_harness")
        source_path.write_text(textwrap.dedent(source), encoding="utf-8", newline="\n")
        command = [
            *cc,
            "-x",
            "c",
            str(source_path),
            str(EVENT_RUNTIME),
            str(ASYNC_RUNTIME),
            "-I",
            str(REPO_ROOT),
            "-o",
            str(exe_path),
        ]
        if os.name != "nt":
            command.append("-pthread")
        compile_result = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, timeout=120)
        if compile_result.returncode != 0:
            raise AssertionError(f"compile failed\nstdout:\n{compile_result.stdout}\nstderr:\n{compile_result.stderr}")
        env = os.environ.copy()
        env["SEM_EVENT_STORE_DIR"] = temp_dir
        return subprocess.run([str(exe_path)], cwd=REPO_ROOT, env=env, text=True, capture_output=True, timeout=30)


class TestEventRuntimeNative(unittest.TestCase):
    def test_fifo_gap_cancel_and_durable_replay(self) -> None:
        result = compile_and_run(
            r'''
            #include "SemanticScript/std/event/native/sem_event_runtime.h"
            #include <stdio.h>
            #include <stdlib.h>
            #include <string.h>

            static int store_path_for_name(const char *stream_name, char *out_path, size_t out_capacity) {
                static const char hex_digits[] = "0123456789abcdef";
                const char *store_dir = getenv("SEM_EVENT_STORE_DIR");
                size_t offset = 0;
                size_t dir_length;
                size_t index;
                int written;

                if (!store_dir || !stream_name || !out_path || out_capacity == 0) return 0;
                dir_length = strlen(store_dir);
                written = snprintf(out_path, out_capacity, "%s%ssem_event_", store_dir,
                    (dir_length > 0 && (store_dir[dir_length - 1] == '/' || store_dir[dir_length - 1] == '\\')) ? "" : "/");
                if (written < 0 || (size_t)written >= out_capacity) return 0;
                offset = (size_t)written;
                for (index = 0; stream_name[index] != '\0'; index += 1) {
                    unsigned char ch = (unsigned char)stream_name[index];
                    if (offset + 2 >= out_capacity) return 0;
                    out_path[offset] = hex_digits[(ch >> 4) & 0x0fU];
                    out_path[offset + 1] = hex_digits[ch & 0x0fU];
                    offset += 2;
                }
                if (offset + strlen(".sseventlog") >= out_capacity) return 0;
                memcpy(out_path + offset, ".sseventlog", strlen(".sseventlog") + 1U);
                return 1;
            }

            static int append_partial_store_record(const char *stream_name) {
                char path[1024];
                unsigned char partial_record[2] = { 0x45U, 0x56U };
                FILE *file;
                if (!store_path_for_name(stream_name, path, sizeof path)) return 0;
                file = fopen(path, "ab");
                if (!file) return 0;
                if (fwrite(partial_record, 1U, sizeof partial_record, file) != sizeof partial_record) {
                    fclose(file);
                    return 0;
                }
                return fclose(file) == 0;
            }

            int main(void) {
                SSAsyncLoop *loop = 0;
                SSAsyncCancelToken *token = 0;
                void *stream = 0;
                void *subscription = 0;
                void *first_future = 0;
                void *second_future = 0;
                char first_type[64];
                char second_type[64];
                long long first_result;
                long long second_result;

                if (ss_async_loop_init(&loop) != SS_ASYNC_OK) return 1;

                stream = ss_event_open_process_stream("fifo-smoke", 8);
                if (!stream) return 2;
                subscription = ss_event_subscribe(stream, "", "", 0, 8);
                if (!subscription) return 3;
                if (ss_event_receive_start(loop, subscription, first_type, (int)sizeof first_type, 0, 0, 0, 0, 1000, 0, &first_future) != SS_EVENT_OK) return 4;
                if (ss_event_receive_start(loop, subscription, second_type, (int)sizeof second_type, 0, 0, 0, 0, 1000, 0, &second_future) != SS_EVENT_OK) return 5;
                if (ss_event_append(stream, "type.one", "", "{}") != 1) return 6;
                if (ss_event_append(stream, "type.two", "", "{}") != 2) return 7;
                first_result = ss_event_receive_await(loop, first_future);
                second_result = ss_event_receive_await(loop, second_future);
                if (first_result != 1 || second_result != 2) return 8;
                if (strcmp(first_type, "type.one") != 0 || strcmp(second_type, "type.two") != 0) return 9;
                if (ss_event_close_subscription(subscription) != SS_EVENT_OK) return 10;
                if (ss_event_close_stream(stream) != SS_EVENT_OK) return 11;

                stream = ss_event_open_process_stream("gap-smoke", 1);
                if (!stream) return 12;
                if (ss_event_append(stream, "gap.one", "", "{}") != 1) return 13;
                if (ss_event_append(stream, "gap.two", "", "{}") != 2) return 14;
                subscription = ss_event_subscribe(stream, "", "", 0, 1);
                if (!subscription) return 15;
                first_result = ss_event_receive(subscription, 0, 0, 0, 0, 0, 0);
                if (first_result != SS_EVENT_ERR_QUEUE_FULL) return 16;
                if (ss_event_close_subscription(subscription) != SS_EVENT_OK) return 17;
                if (ss_event_close_stream(stream) != SS_EVENT_OK) return 18;

                stream = ss_event_open_process_queue("queue-smoke", 2);
                if (!stream) return 34;
                if (ss_event_append(stream, "queue.one", "", "{}") != 1) return 35;
                if (ss_event_append(stream, "queue.two", "", "{}") != 2) return 36;
                if (ss_event_append(stream, "queue.three", "", "{}") != SS_EVENT_ERR_QUEUE_FULL) return 37;
                subscription = ss_event_subscribe(stream, "", "", 0, 2);
                if (!subscription) return 38;
                first_result = ss_event_receive(subscription, first_type, (int)sizeof first_type, 0, 0, 0, 0);
                if (first_result != 1 || strcmp(first_type, "queue.one") != 0) return 39;
                if (ss_event_acknowledge(subscription, first_result) != SS_EVENT_OK) return 40;
                if (ss_event_append(stream, "queue.three", "", "{}") != 3) return 41;
                second_result = ss_event_receive(subscription, second_type, (int)sizeof second_type, 0, 0, 0, 0);
                if (second_result != 2 || strcmp(second_type, "queue.two") != 0) return 42;
                if (ss_event_close_subscription(subscription) != SS_EVENT_OK) return 43;
                if (ss_event_close_stream(stream) != SS_EVENT_OK) return 44;

                stream = ss_event_open_process_stream("filter-capacity-smoke", 8);
                if (!stream) return 45;
                if (ss_event_append(stream, "type.b", "", "{}") != 1) return 46;
                if (ss_event_append(stream, "type.b", "", "{}") != 2) return 47;
                subscription = ss_event_subscribe(stream, "type.a", "", 0, 1);
                if (!subscription) return 48;
                first_result = ss_event_receive(subscription, 0, 0, 0, 0, 0, 0);
                if (first_result != SS_EVENT_NO_EVENT) return 49;
                if (ss_event_append(stream, "type.a", "", "{}") != 3) return 50;
                first_result = ss_event_receive(subscription, first_type, (int)sizeof first_type, 0, 0, 0, 0);
                if (first_result != 3 || strcmp(first_type, "type.a") != 0) return 51;
                if (ss_event_close_subscription(subscription) != SS_EVENT_OK) return 52;
                if (ss_event_close_stream(stream) != SS_EVENT_OK) return 53;

                stream = ss_event_open_process_stream("filtered-gap-smoke", 1);
                if (!stream) return 63;
                subscription = ss_event_subscribe(stream, "type.a", "", 0, 1);
                if (!subscription) return 64;
                if (ss_event_append(stream, "type.a", "", "{}") != 1) return 65;
                if (ss_event_append(stream, "type.b", "", "{}") != 2) return 66;
                first_result = ss_event_receive(subscription, 0, 0, 0, 0, 0, 0);
                if (first_result != SS_EVENT_ERR_QUEUE_FULL) return 67;
                if (ss_event_close_subscription(subscription) != SS_EVENT_OK) return 68;
                if (ss_event_close_stream(stream) != SS_EVENT_OK) return 69;

                {
                    void *first_stream = ss_event_open_process_stream("multi-open-smoke", 8);
                    void *second_stream = ss_event_open_process_stream("multi-open-smoke", 8);
                    if (!first_stream || !second_stream || first_stream == second_stream) return 54;
                    if (ss_event_close_stream(first_stream) != SS_EVENT_OK) return 55;
                    if (ss_event_close_stream(first_stream) != SS_EVENT_ERR_CONFIG) return 56;
                    if (ss_event_append(second_stream, "still.open", "", "{}") != 1) return 57;
                    if (ss_event_close_stream(second_stream) != SS_EVENT_OK) return 58;
                }

                stream = ss_event_open_process_stream("cancel-smoke", 8);
                if (!stream) return 19;
                subscription = ss_event_subscribe(stream, "", "", 0, 8);
                if (!subscription) return 20;
                token = ss_async_cancel_token_create();
                if (!token) return 21;
                if (ss_event_receive_start(loop, subscription, 0, 0, 0, 0, 0, 0, 1000, token, &first_future) != SS_EVENT_OK) return 22;
                ss_async_cancel_token_cancel(token);
                ss_async_cancel_token_destroy(token);
                first_result = ss_event_receive_await(loop, first_future);
                if (first_result != SS_EVENT_ERR_CANCELLED) return 23;
                if (ss_event_close_subscription(subscription) != SS_EVENT_OK) return 24;
                if (ss_event_close_stream(stream) != SS_EVENT_OK) return 25;

                stream = ss_event_open_process_stream("cancelled-receive-does-not-steal", 8);
                if (!stream) return 70;
                subscription = ss_event_subscribe(stream, "", "", 0, 8);
                if (!subscription) return 71;
                token = ss_async_cancel_token_create();
                if (!token) return 72;
                if (ss_event_receive_start(loop, subscription, first_type, (int)sizeof first_type, 0, 0, 0, 0, 1000, token, &first_future) != SS_EVENT_OK) return 73;
                if (ss_event_receive_start(loop, subscription, second_type, (int)sizeof second_type, 0, 0, 0, 0, 1000, 0, &second_future) != SS_EVENT_OK) return 74;
                ss_async_cancel_token_cancel(token);
                ss_async_cancel_token_destroy(token);
                if (ss_event_append(stream, "cancel.skip", "", "{}") != 1) return 75;
                first_result = ss_event_receive_await(loop, first_future);
                second_result = ss_event_receive_await(loop, second_future);
                if (first_result != SS_EVENT_ERR_CANCELLED) return 76;
                if (second_result != 1 || strcmp(second_type, "cancel.skip") != 0) return 77;
                if (ss_event_close_subscription(subscription) != SS_EVENT_OK) return 78;
                if (ss_event_close_stream(stream) != SS_EVENT_OK) return 79;

                stream = ss_event_open_durable_stream("durable-smoke-native", 8);
                if (!stream) return 26;
                first_result = ss_event_append(stream, "durable.one", "", "{\"ok\":true}");
                if (first_result <= 0) return 27;
                if (ss_event_close_stream(stream) != SS_EVENT_OK) return 28;
                stream = ss_event_open_durable_stream("durable-smoke-native", 8);
                if (!stream) return 29;
                subscription = ss_event_subscribe(stream, "durable.one", "", 0, 8);
                if (!subscription) return 30;
                second_result = ss_event_receive(subscription, first_type, (int)sizeof first_type, 0, 0, 0, 0);
                if (second_result != first_result || strcmp(first_type, "durable.one") != 0) return 31;
                if (ss_event_close_subscription(subscription) != SS_EVENT_OK) return 32;
                if (ss_event_close_stream(stream) != SS_EVENT_OK) return 33;

                {
                    void *first_durable = ss_event_open_durable_stream("durable-multi-open-native", 8);
                    void *second_durable = ss_event_open_durable_stream("durable-multi-open-native", 8);
                    long long first_id;
                    long long second_id;
                    if (!first_durable || !second_durable || first_durable == second_durable) return 59;
                    first_id = ss_event_append(first_durable, "durable.multi", "", "{}");
                    second_id = ss_event_append(second_durable, "durable.multi", "", "{}");
                    if (first_id <= 0 || second_id != first_id + 1) return 60;
                    if (ss_event_close_stream(first_durable) != SS_EVENT_OK) return 61;
                    if (ss_event_close_stream(second_durable) != SS_EVENT_OK) return 62;
                }

                stream = ss_event_open_durable_stream("durable-bounded-native", 2);
                if (!stream) return 80;
                if (ss_event_append(stream, "bounded.one", "", "{}") != 1) return 81;
                if (ss_event_append(stream, "bounded.two", "", "{}") != 2) return 82;
                if (ss_event_append(stream, "bounded.three", "", "{}") != 3) return 83;
                subscription = ss_event_subscribe(stream, "", "", 0, 2);
                if (!subscription) return 84;
                if (ss_event_receive(subscription, 0, 0, 0, 0, 0, 0) != SS_EVENT_ERR_QUEUE_FULL) return 85;
                if (ss_event_close_subscription(subscription) != SS_EVENT_OK) return 86;
                subscription = ss_event_subscribe(stream, "", "", 1, 2);
                if (!subscription) return 87;
                first_result = ss_event_receive(subscription, first_type, (int)sizeof first_type, 0, 0, 0, 0);
                second_result = ss_event_receive(subscription, second_type, (int)sizeof second_type, 0, 0, 0, 0);
                if (first_result != 2 || second_result != 3) return 88;
                if (strcmp(first_type, "bounded.two") != 0 || strcmp(second_type, "bounded.three") != 0) return 89;
                if (ss_event_close_subscription(subscription) != SS_EVENT_OK) return 90;
                if (ss_event_close_stream(stream) != SS_EVENT_OK) return 91;

                stream = ss_event_open_durable_stream("durable-filtered-gap-native", 1);
                if (!stream) return 92;
                if (ss_event_append(stream, "type.a", "", "{}") != 1) return 93;
                if (ss_event_append(stream, "type.b", "", "{}") != 2) return 94;
                subscription = ss_event_subscribe(stream, "type.a", "", 0, 1);
                if (!subscription) return 95;
                if (ss_event_receive(subscription, 0, 0, 0, 0, 0, 0) != SS_EVENT_ERR_QUEUE_FULL) return 96;
                if (ss_event_close_subscription(subscription) != SS_EVENT_OK) return 97;
                if (ss_event_close_stream(stream) != SS_EVENT_OK) return 98;

                stream = ss_event_open_durable_stream("durable-torn-native", 8);
                if (!stream) return 99;
                if (ss_event_append(stream, "torn.one", "", "{}") != 1) return 100;
                if (ss_event_close_stream(stream) != SS_EVENT_OK) return 101;
                if (!append_partial_store_record("durable-torn-native")) return 102;
                stream = ss_event_open_durable_stream("durable-torn-native", 8);
                if (!stream) return 103;
                subscription = ss_event_subscribe(stream, "", "", 0, 8);
                if (!subscription) return 104;
                first_result = ss_event_receive(subscription, first_type, (int)sizeof first_type, 0, 0, 0, 0);
                if (first_result != 1 || strcmp(first_type, "torn.one") != 0) return 105;
                if (ss_event_append(stream, "torn.two", "", "{}") != 2) return 106;
                second_result = ss_event_receive(subscription, second_type, (int)sizeof second_type, 0, 0, 0, 0);
                if (second_result != 2 || strcmp(second_type, "torn.two") != 0) return 107;
                if (ss_event_close_subscription(subscription) != SS_EVENT_OK) return 108;
                if (ss_event_close_stream(stream) != SS_EVENT_OK) return 109;

                ss_async_loop_destroy(loop);
                return 0;
            }
            '''
        )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_threaded_append_smoke(self) -> None:
        result = compile_and_run(
            r'''
            #include "SemanticScript/std/event/native/sem_event_runtime.h"

            enum { THREAD_COUNT = 4, EVENTS_PER_THREAD = 25 };

            typedef struct AppendWorker {
                void *stream;
                int worker_index;
                int failed;
            } AppendWorker;

            static void append_worker_run(AppendWorker *worker) {
                int index;
                for (index = 0; index < EVENTS_PER_THREAD; index += 1) {
                    long long event_id = ss_event_append(worker->stream, "thread.event", "", "{}");
                    if (event_id <= 0) {
                        worker->failed = 1;
                        return;
                    }
                }
            }

            #ifdef _WIN32
            #include <windows.h>
            static DWORD WINAPI append_worker_entry(LPVOID user_data) {
                append_worker_run((AppendWorker *)user_data);
                return 0;
            }
            #else
            #include <pthread.h>
            static void *append_worker_entry(void *user_data) {
                append_worker_run((AppendWorker *)user_data);
                return 0;
            }
            #endif

            int main(void) {
                void *stream = ss_event_open_process_stream("thread-smoke", 256);
                void *subscription;
                AppendWorker workers[THREAD_COUNT];
                int index;
                int received_count = 0;
                if (!stream) return 1;
                subscription = ss_event_subscribe(stream, "thread.event", "", 0, 256);
                if (!subscription) return 2;

                #ifdef _WIN32
                {
                    HANDLE threads[THREAD_COUNT];
                    for (index = 0; index < THREAD_COUNT; index += 1) {
                        workers[index].stream = stream;
                        workers[index].worker_index = index;
                        workers[index].failed = 0;
                        threads[index] = CreateThread(0, 0, append_worker_entry, &workers[index], 0, 0);
                        if (threads[index] == 0) return 3;
                    }
                    WaitForMultipleObjects(THREAD_COUNT, threads, TRUE, INFINITE);
                    for (index = 0; index < THREAD_COUNT; index += 1) {
                        CloseHandle(threads[index]);
                    }
                }
                #else
                {
                    pthread_t threads[THREAD_COUNT];
                    for (index = 0; index < THREAD_COUNT; index += 1) {
                        workers[index].stream = stream;
                        workers[index].worker_index = index;
                        workers[index].failed = 0;
                        if (pthread_create(&threads[index], 0, append_worker_entry, &workers[index]) != 0) return 3;
                    }
                    for (index = 0; index < THREAD_COUNT; index += 1) {
                        pthread_join(threads[index], 0);
                    }
                }
                #endif

                for (index = 0; index < THREAD_COUNT; index += 1) {
                    if (workers[index].failed) return 4;
                }
                while (received_count < THREAD_COUNT * EVENTS_PER_THREAD) {
                    long long event_id = ss_event_receive(subscription, 0, 0, 0, 0, 0, 0);
                    if (event_id <= 0) return 5;
                    received_count += 1;
                }
                if (ss_event_close_subscription(subscription) != SS_EVENT_OK) return 6;
                if (ss_event_close_stream(stream) != SS_EVENT_OK) return 7;
                return 0;
            }
            '''
        )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_durable_cross_process_writers_allocate_unique_ids(self) -> None:
        cc = c_compiler_command()
        if cc is None:
            raise unittest.SkipTest("no clang or zig compiler available")
        with tempfile.TemporaryDirectory(prefix="ss_event_cross_process_") as temp_dir:
            temp_path = Path(temp_dir)
            store_path = temp_path / "store"
            store_path.mkdir()
            source_path = temp_path / "durable_cross_process.c"
            exe_path = temp_path / ("durable_cross_process.exe" if os.name == "nt" else "durable_cross_process")
            source_path.write_text(
                textwrap.dedent(
                    r'''
                    #include "SemanticScript/std/event/native/sem_event_runtime.h"
                    #include <stdlib.h>
                    #include <string.h>

                    enum { STREAM_CAPACITY = 256 };

                    int main(int argc, char **argv) {
                        const char *stream_name = "durable-cross-process-native";
                        if (argc < 2) return 1;
                        if (strcmp(argv[1], "write") == 0) {
                            int count;
                            int index;
                            void *stream;
                            if (argc < 3) return 2;
                            count = atoi(argv[2]);
                            stream = ss_event_open_durable_stream(stream_name, STREAM_CAPACITY);
                            if (!stream) return 3;
                            for (index = 0; index < count; index += 1) {
                                long long event_id = ss_event_append(stream, "cross.process", "", "{}");
                                if (event_id <= 0) return 4;
                            }
                            if (ss_event_close_stream(stream) != SS_EVENT_OK) return 5;
                            return 0;
                        }
                        if (strcmp(argv[1], "verify") == 0) {
                            int total;
                            int expected;
                            void *stream;
                            void *subscription;
                            if (argc < 3) return 6;
                            total = atoi(argv[2]);
                            stream = ss_event_open_durable_stream(stream_name, STREAM_CAPACITY);
                            if (!stream) return 7;
                            subscription = ss_event_subscribe(stream, "", "", 0, STREAM_CAPACITY);
                            if (!subscription) return 8;
                            for (expected = 1; expected <= total; expected += 1) {
                                long long event_id = ss_event_receive(subscription, 0, 0, 0, 0, 0, 0);
                                if (event_id != expected) return 9;
                            }
                            if (ss_event_close_subscription(subscription) != SS_EVENT_OK) return 10;
                            if (ss_event_close_stream(stream) != SS_EVENT_OK) return 11;
                            return 0;
                        }
                        return 12;
                    }
                    '''
                ),
                encoding="utf-8",
                newline="\n",
            )
            command = [
                *cc,
                "-x",
                "c",
                str(source_path),
                str(EVENT_RUNTIME),
                str(ASYNC_RUNTIME),
                "-I",
                str(REPO_ROOT),
                "-o",
                str(exe_path),
            ]
            if os.name != "nt":
                command.append("-pthread")
            compile_result = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, timeout=120)
            if compile_result.returncode != 0:
                raise AssertionError(f"compile failed\nstdout:\n{compile_result.stdout}\nstderr:\n{compile_result.stderr}")
            env = os.environ.copy()
            env["SEM_EVENT_STORE_DIR"] = str(store_path)
            process_count = 4
            events_per_process = 25
            processes = [
                subprocess.Popen(
                    [str(exe_path), "write", str(events_per_process)],
                    cwd=REPO_ROOT,
                    env=env,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                for _ in range(process_count)
            ]
            for process in processes:
                stdout, stderr = process.communicate(timeout=30)
                if process.returncode != 0:
                    raise AssertionError(f"writer failed rc={process.returncode}\nstdout:\n{stdout}\nstderr:\n{stderr}")
            verify_result = subprocess.run(
                [str(exe_path), "verify", str(process_count * events_per_process)],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                capture_output=True,
                timeout=30,
            )
            self.assertEqual(0, verify_result.returncode, verify_result.stderr)


if __name__ == "__main__":
    unittest.main()
