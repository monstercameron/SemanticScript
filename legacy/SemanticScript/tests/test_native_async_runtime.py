import os
import shutil
import shlex
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ASYNC_RUNTIME = REPO_ROOT / "SemanticScript" / "runtime" / "native_async" / "sem_async_runtime.c"


def c_compiler_command() -> list[str] | None:
    configured = os.environ.get("SEMSC_CLANG")
    if configured:
        return shlex.split(configured)
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
    with tempfile.TemporaryDirectory(prefix="ss_async_native_") as temp_dir:
        temp_path = Path(temp_dir)
        source_path = temp_path / "async_runtime_harness.c"
        exe_path = temp_path / ("async_runtime_harness.exe" if os.name == "nt" else "async_runtime_harness")
        source_path.write_text(textwrap.dedent(source), encoding="utf-8", newline="\n")
        command = [
            *cc,
            "-x",
            "c",
            str(source_path),
            str(ASYNC_RUNTIME),
            "-I",
            str(REPO_ROOT),
            "-o",
            str(exe_path),
        ]
        if os.name != "nt":
            command.append("-pthread")
        compile_result = subprocess.run(
            command,
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            timeout=120,
        )
        if compile_result.returncode != 0:
            raise AssertionError(
                f"compile failed\nstdout:\n{compile_result.stdout}\nstderr:\n{compile_result.stderr}"
            )
        return subprocess.run(
            [str(exe_path)],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            timeout=30,
        )


class TestNativeAsyncRuntime(unittest.TestCase):
    def test_future_continuations_run_from_loop_not_completion_call(self) -> None:
        result = compile_and_run(
            r'''
            #include "SemanticScript/runtime/native_async/sem_async_runtime.h"

            typedef struct CallbackState {
                SSAsyncLoop *loop;
                SSFuture *future;
                int resume_count;
                int nested_count;
                int timer_count;
                int order_index;
                int order_values[3];
            } CallbackState;

            static void nested_resume(void *user_data) {
                CallbackState *state = (CallbackState *)user_data;
                state->nested_count += 1;
            }

            static void first_resume(void *user_data) {
                CallbackState *state = (CallbackState *)user_data;
                state->resume_count += 1;
            }

            static void stop_resume(void *user_data) {
                CallbackState *state = (CallbackState *)user_data;
                state->resume_count += 1;
                (void)ss_async_loop_stop(state->loop);
            }

            static void ordered_first_resume(void *user_data) {
                CallbackState *state = (CallbackState *)user_data;
                state->order_values[state->order_index] = 1;
                state->order_index += 1;
            }

            static void ordered_second_resume(void *user_data) {
                CallbackState *state = (CallbackState *)user_data;
                state->order_values[state->order_index] = 2;
                state->order_index += 1;
            }

            static void register_nested_resume(void *user_data) {
                CallbackState *state = (CallbackState *)user_data;
                state->resume_count += 1;
                (void)ss_async_future_on_ready(state->future, nested_resume, state);
                if (state->nested_count != 0) {
                    state->nested_count = -100;
                }
            }

            static void timer_stop_and_complete(void *user_data) {
                CallbackState *state = (CallbackState *)user_data;
                state->timer_count += 1;
                (void)ss_async_future_complete(state->future, SS_ASYNC_OK, state);
                (void)ss_async_loop_stop(state->loop);
            }

            int main(void) {
                CallbackState state;
                SSFuture *future;

                state.loop = 0;
                state.future = 0;
                state.resume_count = 0;
                state.nested_count = 0;
                state.timer_count = 0;
                state.order_index = 0;
                state.order_values[0] = 0;
                state.order_values[1] = 0;
                state.order_values[2] = 0;

                if (ss_async_loop_init(&state.loop) != SS_ASYNC_OK) return 1;

                future = ss_async_future_create(state.loop);
                if (future == 0) return 2;
                if (ss_async_future_on_ready(future, first_resume, &state) != SS_ASYNC_OK) return 3;
                if (state.resume_count != 0) return 4;
                if (ss_async_future_complete(future, SS_ASYNC_OK, &state) != SS_ASYNC_OK) return 5;
                if (state.resume_count != 0) return 6;
                if (ss_async_loop_run_once(state.loop) != SS_ASYNC_OK) return 7;
                if (state.resume_count != 1) return 8;
                ss_async_future_destroy(future);

                future = ss_async_future_create(state.loop);
                if (future == 0) return 9;
                if (ss_async_future_complete(future, SS_ASYNC_OK, &state) != SS_ASYNC_OK) return 10;
                if (ss_async_future_on_ready(future, first_resume, &state) != SS_ASYNC_OK) return 11;
                if (state.resume_count != 1) return 12;
                if (ss_async_loop_run_once(state.loop) != SS_ASYNC_OK) return 13;
                if (state.resume_count != 2) return 14;
                ss_async_future_destroy(future);

                future = ss_async_future_create(state.loop);
                if (future == 0) return 15;
                state.future = future;
                if (ss_async_future_complete(future, SS_ASYNC_OK, &state) != SS_ASYNC_OK) return 16;
                if (ss_async_future_on_ready(future, register_nested_resume, &state) != SS_ASYNC_OK) return 17;
                if (ss_async_loop_run_once(state.loop) != SS_ASYNC_OK) return 18;
                if (state.resume_count != 3) return 19;
                if (state.nested_count != 1) return 20;
                ss_async_future_destroy(future);

                future = ss_async_future_create(state.loop);
                if (future == 0) return 21;
                if (ss_async_future_on_ready(future, ordered_first_resume, &state) != SS_ASYNC_OK) return 22;
                if (ss_async_future_on_ready(future, ordered_second_resume, &state) != SS_ASYNC_OK) return 23;
                if (ss_async_future_complete(future, SS_ASYNC_OK, &state) != SS_ASYNC_OK) return 24;
                if (ss_async_loop_run_once(state.loop) != SS_ASYNC_OK) return 25;
                if (state.order_index != 2) return 26;
                if (state.order_values[0] != 1 || state.order_values[1] != 2) return 27;
                ss_async_future_destroy(future);

                future = ss_async_future_create(state.loop);
                if (future == 0) return 28;
                if (ss_async_future_on_ready(future, first_resume, &state) != SS_ASYNC_OK) return 29;
                if (ss_async_future_complete(future, SS_ASYNC_OK, &state) != SS_ASYNC_OK) return 30;
                ss_async_future_destroy(future);
                if (ss_async_loop_run_once(state.loop) != SS_ASYNC_OK) return 31;
                if (state.resume_count != 3) return 32;

                future = ss_async_future_create(state.loop);
                if (future == 0) return 33;
                if (ss_async_future_on_ready(future, stop_resume, &state) != SS_ASYNC_OK) return 34;
                if (ss_async_future_complete(future, SS_ASYNC_OK, &state) != SS_ASYNC_OK) return 35;
                if (ss_async_loop_run(state.loop) != SS_ASYNC_OK) return 36;
                if (state.resume_count != 4) return 37;
                ss_async_future_destroy(future);

                {
                    SSAsyncTimer *timer = 0;
                    int guard = 0;
                    future = ss_async_future_create(state.loop);
                    if (future == 0) return 38;
                    state.future = future;
                    if (ss_async_future_on_ready(future, first_resume, &state) != SS_ASYNC_OK) return 39;
                    if (ss_async_timer_start(state.loop, 1, timer_stop_and_complete, &state, &timer) != SS_ASYNC_OK) return 40;
                    while (state.timer_count == 0 && guard < 1000) {
                        if (ss_async_loop_run_once(state.loop) != SS_ASYNC_OK) return 41;
                        guard += 1;
                    }
                    if (state.timer_count != 1) return 42;
                    if (state.resume_count != 4) return 43;
                    ss_async_future_destroy(future);
                    ss_async_timer_destroy(timer);
                }

                {
                    SSAsyncCancelToken *token = ss_async_cancel_token_create();
                    if (token == 0) return 44;
                    if (ss_async_cancel_token_is_cancelled(token)) return 45;
                    if (!ss_async_cancel_token_retain(token)) return 46;
                    ss_async_cancel_token_cancel(token);
                    if (!ss_async_cancel_token_is_cancelled(token)) return 47;
                    ss_async_cancel_token_destroy(token);
                    if (!ss_async_cancel_token_is_cancelled(token)) return 48;
                    ss_async_cancel_token_release(token);
                }

                ss_async_loop_destroy(state.loop);
                return 0;
            }
            '''
        )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_negative_api_inputs_return_config_or_safe_defaults(self) -> None:
        result = compile_and_run(
            r'''
            #include "SemanticScript/runtime/native_async/sem_async_runtime.h"

            static void noop_resume(void *user_data) {
                (void)user_data;
            }

            static void noop_work(void *user_data) {
                (void)user_data;
            }

            int main(void) {
                SSAsyncLoop *loop = 0;
                SSFuture *future = 0;
                SSAsyncTimer *timer = 0;
                long not_token = 0;

                if (ss_async_loop_init(0) != SS_ASYNC_ERR_CONFIG) return 1;
                if (ss_async_loop_run(0) != SS_ASYNC_ERR_CONFIG) return 2;
                if (ss_async_loop_run_once(0) != SS_ASYNC_ERR_CONFIG) return 3;
                if (ss_async_loop_stop(0) != SS_ASYNC_ERR_CONFIG) return 4;
                if (ss_async_loop_native_handle(0) != 0) return 5;
                ss_async_loop_destroy(0);

                if (ss_async_future_create(0) != 0) return 6;
                if (ss_async_future_on_ready(0, noop_resume, 0) != SS_ASYNC_ERR_CONFIG) return 7;
                if (ss_async_future_complete(0, SS_ASYNC_OK, 0) != SS_ASYNC_ERR_CONFIG) return 8;
                if (ss_async_future_cancel(0) != SS_ASYNC_ERR_CONFIG) return 9;
                if (ss_async_future_await(0, 0) != SS_ASYNC_ERR_CONFIG) return 10;
                if (ss_async_future_is_ready(0) != 0) return 11;
                if (ss_async_future_status(0) != SS_ASYNC_ERR_CONFIG) return 12;
                if (ss_async_future_result(0) != 0) return 13;
                ss_async_future_destroy(0);

                if (ss_async_timer_start(0, 1, noop_resume, 0, &timer) != SS_ASYNC_ERR_CONFIG) return 14;
                if (ss_async_timer_start(loop, 1, 0, 0, &timer) != SS_ASYNC_ERR_CONFIG) return 15;
                if (ss_async_timer_start(loop, 1, noop_resume, 0, 0) != SS_ASYNC_ERR_CONFIG) return 16;
                if (ss_async_timer_cancel(0) != SS_ASYNC_ERR_CONFIG) return 17;
                ss_async_timer_destroy(0);

                ss_async_cancel_token_cancel(0);
                if (ss_async_cancel_token_is_cancelled(0) != 0) return 18;
                if (ss_async_cancel_token_retain(0) != 0) return 19;
                ss_async_cancel_token_release(0);
                ss_async_cancel_token_destroy(0);
                ss_async_cancel_token_cancel((SSAsyncCancelToken *)&not_token);
                if (ss_async_cancel_token_is_cancelled((SSAsyncCancelToken *)&not_token) != 0) return 20;
                if (ss_async_cancel_token_retain((SSAsyncCancelToken *)&not_token) != 0) return 21;
                ss_async_cancel_token_release((SSAsyncCancelToken *)&not_token);
                ss_async_cancel_token_destroy((SSAsyncCancelToken *)&not_token);

                if (ss_async_queue_work(0, noop_work, 0, 0) != SS_ASYNC_ERR_CONFIG) return 22;
                if (ss_async_loop_init(&loop) != SS_ASYNC_OK) return 23;
                if (ss_async_queue_work(loop, 0, 0, 0) != SS_ASYNC_ERR_CONFIG) return 24;
                future = ss_async_future_create(loop);
                if (future == 0) return 25;
                if (ss_async_future_on_ready(future, 0, 0) != SS_ASYNC_ERR_CONFIG) return 26;
                if (ss_async_future_await(0, future) != SS_ASYNC_ERR_CONFIG) return 27;
                if (ss_async_future_await(loop, 0) != SS_ASYNC_ERR_CONFIG) return 28;
                ss_async_future_destroy(future);
                ss_async_loop_destroy(loop);
                return 0;
            }
            '''
        )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_edge_status_timer_work_and_stop_semantics(self) -> None:
        result = compile_and_run(
            r'''
            #include "SemanticScript/runtime/native_async/sem_async_runtime.h"

            typedef struct EdgeState {
                SSAsyncLoop *loop;
                SSFuture *future;
                SSAsyncTimer *second_timer;
                int first_timer_count;
                int second_timer_count;
                int work_count;
                int after_count;
                int after_status;
                int resume_count;
                int second_resume_count;
            } EdgeState;

            static void work_cb(void *user_data) {
                EdgeState *state = (EdgeState *)user_data;
                state->work_count += 1;
            }

            static void after_work_cb(void *user_data, int status) {
                EdgeState *state = (EdgeState *)user_data;
                state->after_count += 1;
                state->after_status = status;
            }

            static void first_timer_cb(void *user_data) {
                EdgeState *state = (EdgeState *)user_data;
                state->first_timer_count += 1;
                ss_async_timer_destroy(state->second_timer);
                state->second_timer = 0;
            }

            static void second_timer_cb(void *user_data) {
                EdgeState *state = (EdgeState *)user_data;
                state->second_timer_count += 1;
            }

            static void stop_resume(void *user_data) {
                EdgeState *state = (EdgeState *)user_data;
                state->resume_count += 1;
                (void)ss_async_loop_stop(state->loop);
            }

            static void second_resume(void *user_data) {
                EdgeState *state = (EdgeState *)user_data;
                state->second_resume_count += 1;
            }

            int main(void) {
                EdgeState state;
                SSFuture *future;
                SSFuture *second_future;
                SSAsyncTimer *first_timer = 0;
                int result_value = 1234;
                int replacement_value = 5678;

                state.loop = 0;
                state.future = 0;
                state.second_timer = 0;
                state.first_timer_count = 0;
                state.second_timer_count = 0;
                state.work_count = 0;
                state.after_count = 0;
                state.after_status = -1;
                state.resume_count = 0;
                state.second_resume_count = 0;

                if (ss_async_loop_init(&state.loop) != SS_ASYNC_OK) return 1;

                future = ss_async_future_create(state.loop);
                if (future == 0) return 2;
                if (ss_async_future_complete(future, SS_ASYNC_ERR_TIMEOUT, &result_value) != SS_ASYNC_OK) return 3;
                if (!ss_async_future_is_ready(future)) return 4;
                if (ss_async_future_status(future) != SS_ASYNC_ERR_TIMEOUT) return 5;
                if (ss_async_future_result(future) != &result_value) return 6;
                if (ss_async_future_complete(future, SS_ASYNC_OK, &replacement_value) != SS_ASYNC_OK) return 7;
                if (ss_async_future_status(future) != SS_ASYNC_ERR_TIMEOUT) return 8;
                if (ss_async_future_result(future) != &result_value) return 9;
                ss_async_future_destroy(future);

                future = ss_async_future_create(state.loop);
                if (future == 0) return 10;
                if (ss_async_future_cancel(future) != SS_ASYNC_OK) return 11;
                if (!ss_async_future_is_ready(future)) return 12;
                if (ss_async_future_status(future) != SS_ASYNC_ERR_CANCELLED) return 13;
                ss_async_future_destroy(future);

                if (ss_async_queue_work(state.loop, work_cb, after_work_cb, &state) != SS_ASYNC_OK) return 14;
                if (state.work_count != 1) return 15;
                if (state.after_count != 1) return 16;
                if (state.after_status != SS_ASYNC_OK) return 17;
                if (ss_async_queue_work(state.loop, work_cb, 0, &state) != SS_ASYNC_OK) return 18;
                if (state.work_count != 2) return 19;
                if (state.after_count != 1) return 20;

                if (ss_async_timer_start(state.loop, 60000, second_timer_cb, &state, &state.second_timer) != SS_ASYNC_OK) return 21;
                if (ss_async_timer_start(state.loop, 0, first_timer_cb, &state, &first_timer) != SS_ASYNC_OK) return 22;
                if (ss_async_loop_run_once(state.loop) != SS_ASYNC_OK) return 23;
                if (state.first_timer_count != 1) return 24;
                if (state.second_timer_count != 0) return 25;
                ss_async_timer_destroy(first_timer);

                state.second_timer = 0;
                if (ss_async_timer_start(state.loop, ~(unsigned long long)0, second_timer_cb, &state, &state.second_timer) != SS_ASYNC_OK) return 26;
                if (ss_async_loop_run_once(state.loop) != SS_ASYNC_OK) return 27;
                if (state.second_timer_count != 0) return 28;
                ss_async_timer_destroy(state.second_timer);
                state.second_timer = 0;

                if (ss_async_timer_start(state.loop, ~(unsigned long long)0, second_timer_cb, &state, &state.second_timer) != SS_ASYNC_OK) return 29;
                if (ss_async_timer_start(state.loop, 0, first_timer_cb, &state, &first_timer) != SS_ASYNC_OK) return 30;
                if (ss_async_loop_run(state.loop) != SS_ASYNC_OK) return 31;
                if (state.first_timer_count != 2) return 32;
                if (state.second_timer_count != 0) return 33;
                ss_async_timer_destroy(first_timer);

                future = ss_async_future_create(state.loop);
                second_future = ss_async_future_create(state.loop);
                if (future == 0 || second_future == 0) return 34;
                if (ss_async_future_on_ready(future, stop_resume, &state) != SS_ASYNC_OK) return 35;
                if (ss_async_future_on_ready(second_future, second_resume, &state) != SS_ASYNC_OK) return 36;
                if (ss_async_future_complete(future, SS_ASYNC_OK, &state) != SS_ASYNC_OK) return 37;
                if (ss_async_future_complete(second_future, SS_ASYNC_OK, &state) != SS_ASYNC_OK) return 38;
                if (ss_async_loop_run(state.loop) != SS_ASYNC_OK) return 39;
                if (state.resume_count != 1) return 40;
                if (state.second_resume_count != 0) return 41;
                if (ss_async_loop_run_once(state.loop) != SS_ASYNC_OK) return 42;
                if (state.second_resume_count != 1) return 43;
                ss_async_future_destroy(future);
                ss_async_future_destroy(second_future);

                ss_async_loop_destroy(state.loop);
                return 0;
            }
            '''
        )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_deterministic_fuzz_future_queue_sequences(self) -> None:
        result = compile_and_run(
            r'''
            #include "SemanticScript/runtime/native_async/sem_async_runtime.h"

            enum { FUZZ_COUNT = 64 };

            typedef struct FuzzState FuzzState;

            typedef struct FuzzItem {
                FuzzState *state;
                SSFuture *future;
                int id;
                int expected;
                int ran;
            } FuzzItem;

            struct FuzzState {
                SSAsyncLoop *loop;
                FuzzItem items[FUZZ_COUNT];
                int actual_order[FUZZ_COUNT];
                int expected_order[FUZZ_COUNT];
                int run_count;
                int expected_count;
                unsigned int checksum;
            };

            static void fuzz_resume(void *user_data) {
                FuzzItem *item = (FuzzItem *)user_data;
                item->state->actual_order[item->state->run_count] = item->id;
                item->ran += 1;
                item->state->run_count += 1;
                item->state->checksum = (item->state->checksum * 33u) ^ (unsigned int)(item->id + 17);
            }

            int main(void) {
                FuzzState state;
                int index;
                int step;

                state.loop = 0;
                state.run_count = 0;
                state.expected_count = 0;
                state.checksum = 2166136261u;
                if (ss_async_loop_init(&state.loop) != SS_ASYNC_OK) return 1;

                for (index = 0; index < FUZZ_COUNT; index += 1) {
                    state.actual_order[index] = -1;
                    state.expected_order[index] = -1;
                    state.items[index].state = &state;
                    state.items[index].future = ss_async_future_create(state.loop);
                    state.items[index].id = index;
                    state.items[index].expected = 1;
                    state.items[index].ran = 0;
                    if (state.items[index].future == 0) return 2;
                    if (ss_async_future_on_ready(state.items[index].future, fuzz_resume, &state.items[index]) != SS_ASYNC_OK) return 3;
                }

                for (step = 0; step < FUZZ_COUNT; step += 1) {
                    index = (step * 17 + 5) & (FUZZ_COUNT - 1);
                    if (ss_async_future_complete(state.items[index].future, SS_ASYNC_OK, &state.items[index]) != SS_ASYNC_OK) return 4;
                    if (ss_async_future_complete(state.items[index].future, SS_ASYNC_ERR_ENGINE, 0) != SS_ASYNC_OK) return 5;
                    if ((index % 5) == 0 || (index % 11) == 0) {
                        state.items[index].expected = 0;
                        ss_async_future_destroy(state.items[index].future);
                        state.items[index].future = 0;
                    } else {
                        state.expected_order[state.expected_count] = index;
                        state.expected_count += 1;
                    }
                }

                if (state.run_count != 0) return 6;
                if (ss_async_loop_run_once(state.loop) != SS_ASYNC_OK) return 7;
                if (state.run_count != state.expected_count) return 8;

                for (index = 0; index < state.expected_count; index += 1) {
                    if (state.actual_order[index] != state.expected_order[index]) return 9;
                }

                for (index = 0; index < FUZZ_COUNT; index += 1) {
                    if (state.items[index].ran != state.items[index].expected) return 10;
                    if (state.items[index].future != 0) {
                        ss_async_future_destroy(state.items[index].future);
                        state.items[index].future = 0;
                    }
                }
                if (state.checksum == 2166136261u && state.expected_count > 0) return 11;
                ss_async_loop_destroy(state.loop);
                return 0;
            }
            '''
        )
        self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
