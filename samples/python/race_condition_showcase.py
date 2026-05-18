from threading import Lock, Thread
import time


# Demonstrates a deterministic lost-update race by splitting read and write with
# a barrier-like busy wait, then shows the lock-based fix.
def run_racy_increment(thread_count, increments_per_thread):
    shared = {"value": 0, "turn": 0}

    def incrementer(thread_id):
        for _ in range(increments_per_thread):
            observed_value = shared["value"]
            expected_turn = shared["turn"]

            while shared["turn"] == expected_turn:
                time.sleep(0)

            shared["value"] = observed_value + 1

        shared["turn"] += 1

    threads = [
        Thread(target=incrementer, args=(thread_id,))
        for thread_id in range(thread_count)
    ]

    for thread in threads:
        thread.start()

    for _ in range(thread_count * increments_per_thread + thread_count):
        shared["turn"] += 1
        time.sleep(0)

    for thread in threads:
        thread.join()

    return shared["value"]


def run_locked_increment(thread_count, increments_per_thread):
    shared = {"value": 0}
    lock = Lock()

    def incrementer():
        for _ in range(increments_per_thread):
            with lock:
                shared["value"] += 1

    threads = [Thread(target=incrementer) for _ in range(thread_count)]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    return shared["value"]


def main():
    thread_count = 4
    increments_per_thread = 25
    expected_value = thread_count * increments_per_thread
    racy_value = run_racy_increment(thread_count, increments_per_thread)
    locked_value = run_locked_increment(thread_count, increments_per_thread)

    print("Race Condition Showcase")
    print("=======================")
    print("expected={}".format(expected_value))
    print("racyValue={}".format(racy_value))
    print("lockedValue={}".format(locked_value))
    print("racyLostUpdates={}".format(expected_value - racy_value))
    print("lockedCorrect={}".format(locked_value == expected_value))


if __name__ == "__main__":
    main()
