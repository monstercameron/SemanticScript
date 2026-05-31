#ifndef SEM_ASYNC_RUNTIME_H
#define SEM_ASYNC_RUNTIME_H

#ifdef __cplusplus
extern "C" {
#endif

typedef struct SSAsyncLoop SSAsyncLoop;
typedef struct SSFuture SSFuture;
typedef struct SSAsyncTimer SSAsyncTimer;
typedef struct SSAsyncCancelToken SSAsyncCancelToken;

typedef void (*SSAsyncResumeFn)(void *user_data);
typedef void (*SSAsyncWorkFn)(void *user_data);
typedef void (*SSAsyncAfterWorkFn)(void *user_data, int status);

enum {
    SS_ASYNC_OK = 0,
    SS_ASYNC_ERR_CONFIG = 1,
    SS_ASYNC_ERR_RUNTIME_UNAVAILABLE = 2,
    SS_ASYNC_ERR_ENGINE = 3,
    SS_ASYNC_ERR_CANCELLED = 4,
    SS_ASYNC_ERR_TIMEOUT = 5
};

int ss_async_loop_init(SSAsyncLoop **out_loop);
int ss_async_loop_run(SSAsyncLoop *loop);
int ss_async_loop_run_once(SSAsyncLoop *loop);
int ss_async_loop_stop(SSAsyncLoop *loop);
void ss_async_loop_destroy(SSAsyncLoop *loop);
void *ss_async_loop_native_handle(SSAsyncLoop *loop);

SSFuture *ss_async_future_create(SSAsyncLoop *loop);
int ss_async_future_on_ready(
    SSFuture *future,
    SSAsyncResumeFn resume,
    void *user_data
);
int ss_async_future_complete(SSFuture *future, int status, void *result);
int ss_async_future_cancel(SSFuture *future);
int ss_async_future_await(SSAsyncLoop *loop, SSFuture *future);
int ss_async_future_is_ready(const SSFuture *future);
int ss_async_future_status(const SSFuture *future);
void *ss_async_future_result(const SSFuture *future);
void ss_async_future_destroy(SSFuture *future);

int ss_async_timer_start(
    SSAsyncLoop *loop,
    unsigned long long timeout_ms,
    SSAsyncResumeFn callback,
    void *user_data,
    SSAsyncTimer **out_timer
);
int ss_async_timer_cancel(SSAsyncTimer *timer);
void ss_async_timer_destroy(SSAsyncTimer *timer);

SSAsyncCancelToken *ss_async_cancel_token_create(void);
void ss_async_cancel_token_cancel(SSAsyncCancelToken *token);
int ss_async_cancel_token_is_cancelled(const void *token);
int ss_async_cancel_token_retain(void *token);
void ss_async_cancel_token_release(void *token);
void ss_async_cancel_token_destroy(SSAsyncCancelToken *token);

int ss_async_queue_work(
    SSAsyncLoop *loop,
    SSAsyncWorkFn work,
    SSAsyncAfterWorkFn after_work,
    void *user_data
);

#ifdef __cplusplus
}
#endif

#endif
