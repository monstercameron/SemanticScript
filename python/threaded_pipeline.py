from queue import Queue
from threading import Event, Lock, Thread
import time


# Multi-stage threaded pipeline with retries, cancellation plumbing, metrics,
# and deterministic final reporting. Uses only Python standard library.
WORKER_COUNT = 3
STOP_SENTINEL = object()


def build_task(task_id, value, attempt=1):
    return {
        "task_id": task_id,
        "value": value,
        "attempt": attempt,
    }


def should_fail_once(task):
    return task["value"] in (5, 8) and task["attempt"] == 1


def transform_value(value):
    # Small deterministic delay creates real interleaving without making tests slow.
    time.sleep(0.005 * (value % 3))
    return value * value


def worker(worker_id, input_queue, output_queue, stop_event, metrics, metrics_lock):
    while not stop_event.is_set():
        task = input_queue.get()

        try:
            if task is STOP_SENTINEL:
                return

            with metrics_lock:
                metrics["started"] += 1

            if should_fail_once(task):
                retry_task = build_task(task["task_id"], task["value"], task["attempt"] + 1)
                input_queue.put(retry_task)

                with metrics_lock:
                    metrics["retries"] += 1

                continue

            transformed_value = transform_value(task["value"])
            output_queue.put({
                "task_id": task["task_id"],
                "worker_id": worker_id,
                "input": task["value"],
                "attempt": task["attempt"],
                "output": transformed_value,
            })

            with metrics_lock:
                metrics["completed"] += 1
        finally:
            input_queue.task_done()


def run_pipeline():
    input_queue = Queue()
    output_queue = Queue()
    stop_event = Event()
    metrics_lock = Lock()
    metrics = {
        "started": 0,
        "completed": 0,
        "retries": 0,
    }

    workers = [
        Thread(
            target=worker,
            args=(worker_id, input_queue, output_queue, stop_event, metrics, metrics_lock),
            name="pipeline-worker-{}".format(worker_id),
        )
        for worker_id in range(1, WORKER_COUNT + 1)
    ]

    for thread in workers:
        thread.start()

    for task_id, value in enumerate([2, 3, 5, 8, 13, 21], start=1):
        input_queue.put(build_task(task_id, value))

    input_queue.join()

    for _ in workers:
        input_queue.put(STOP_SENTINEL)

    for thread in workers:
        thread.join()

    results = []
    while not output_queue.empty():
        results.append(output_queue.get())

    results.sort(key=lambda item: item["task_id"])

    return metrics, results


def main():
    metrics, results = run_pipeline()

    print("Threaded Pipeline")
    print("=================")

    for result in results:
        print(
            "task={task_id} input={input} output={output} attempt={attempt}".format(
                **result
            )
        )

    print("metrics started={started} completed={completed} retries={retries}".format(**metrics))


if __name__ == "__main__":
    main()
