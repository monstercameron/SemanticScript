/*
 * harness_event.c — R-134 native-runtime safety harness for the event stream
 * pub/sub runtime (ss_event.c). Exercises the full subscription/stream lifecycle
 * — including the orderings that USED to be use-after-free / double-free before
 * R-131 (closeStream-before-closeSubscription, double closeStream, append/
 * subscribe after close) — as NORMAL, correct usage. Built with ASAN+UBSAN in CI
 * (.github/workflows/native-safety.yml); a clean run must report ZERO findings.
 *
 * This is the "passes with zero findings" side of R-134; seed_uaf.c is the
 * "sanitizer actually catches a planted bug" side.
 */
#include <assert.h>
#include <stdio.h>

#include "../../semanticscript/runtime/ss_event.c"

int main(void) {
    /* closeStream before closeSubscription: the subscription is orphaned, so a
     * later receive returns 0 instead of dereferencing the freed stream. */
    long long s = ss_event_open_stream("a", 16);
    assert(s);
    long long sub = ss_event_subscribe(s, "t", "k");
    assert(sub);
    ss_event_append(s, "t", "k", "p");
    ss_event_close_stream(s);
    assert(ss_event_receive(sub) == 0);
    ss_event_close_subscription(sub);

    /* double closeStream is a no-op, not a double free */
    long long s2 = ss_event_open_stream("b", 4);
    ss_event_close_stream(s2);
    ss_event_close_stream(s2);

    /* append / subscribe after close are rejected, not a deref of freed memory */
    long long s3 = ss_event_open_stream("c", 4);
    ss_event_close_stream(s3);
    assert(ss_event_append(s3, "t", "k", "p") == 0);
    assert(ss_event_subscribe(s3, "t", "k") == 0);

    /* correct order end-to-end: subscribe, append, receive in FIFO, close */
    long long s4 = ss_event_open_stream("d", 4);
    long long sub4 = ss_event_subscribe(s4, "t", "k");
    assert(ss_event_append(s4, "t", "k", "p") == 1);
    assert(ss_event_receive(sub4) == 1);
    assert(ss_event_receive(sub4) == 0);
    ss_event_close_subscription(sub4);
    ss_event_close_stream(s4);

    /* a queue that grows past its initial capacity (exercises the realloc path) */
    long long s5 = ss_event_open_stream("e", 2);
    long long sub5 = ss_event_subscribe(s5, "t", "k");
    for (int i = 0; i < 50; i++) {
        assert(ss_event_append(s5, "t", "k", "p") == i + 1);
    }
    long long seen = 0;
    while (ss_event_receive(sub5) != 0) {
        seen++;
    }
    assert(seen == 50);
    ss_event_close_subscription(sub5);
    ss_event_close_stream(s5);

    /* an absurd capacity is refused, not allocated */
    assert(ss_event_open_stream("f", (1LL << 30)) == 0);

    /* R-196: a stale subscription handle is rejected by the live-subscription
     * registry instead of dereferencing freed memory. A double closeSubscription
     * is a no-op (not a double free), and a receive after closeSubscription
     * returns 0 (not a use-after-free of the freed sub). */
    long long s6 = ss_event_open_stream("g", 4);
    long long sub6 = ss_event_subscribe(s6, "t", "k");
    assert(sub6);
    ss_event_append(s6, "t", "k", "p");
    ss_event_close_subscription(sub6);
    ss_event_close_subscription(sub6);     /* double close: no-op */
    assert(ss_event_receive(sub6) == 0);   /* receive after close: safe 0 */
    ss_event_close_stream(s6);

    printf("harness_event: OK\n");
    return 0;
}
