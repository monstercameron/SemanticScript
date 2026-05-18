from dataclasses import dataclass, field
from queue import PriorityQueue
from threading import Lock, Thread
import time


# Priority scheduler with cancellation and retry. Lower numeric priority runs
# first. Queue entries use numeric priority plus sequence so stop messages never
# need to be compared with normal task objects.
STOP_TASK = None


@dataclass(order=True)
class ScheduledTask:
    priority: int
    sequence: int
    task_id: str = field(compare=False)
    duration: float = field(compare=False)
    should_fail_once: bool = field(compare=False, default=False)
    attempt: int = field(compare=False, default=1)


def scheduler_worker(worker_id, task_queue, cancel_event, results, results_lock):
    while True:
        _priority, _sequence, scheduled_task = task_queue.get()

        try:
            if scheduled_task is STOP_TASK:
                return

            with cancel_event["lock"]:
                task_is_cancelled = scheduled_task.task_id in cancel_event["task_ids"]

            if task_is_cancelled:
                with results_lock:
                    results.append({
                        "task_id": scheduled_task.task_id,
                        "status": "cancelled",
                        "attempt": scheduled_task.attempt,
                        "worker_id": worker_id,
                    })
                continue

            time.sleep(scheduled_task.duration)

            if scheduled_task.should_fail_once and scheduled_task.attempt == 1:
                retry_task = ScheduledTask(
                    priority=scheduled_task.priority + 1,
                    sequence=scheduled_task.sequence + 100,
                    task_id=scheduled_task.task_id,
                    duration=scheduled_task.duration,
                    should_fail_once=False,
                    attempt=2,
                )
                task_queue.put((retry_task.priority, retry_task.sequence, retry_task))

                with results_lock:
                    results.append({
                        "task_id": scheduled_task.task_id,
                        "status": "retry",
                        "attempt": scheduled_task.attempt,
                        "worker_id": worker_id,
                    })
                continue

            with results_lock:
                results.append({
                    "task_id": scheduled_task.task_id,
                    "status": "done",
                    "attempt": scheduled_task.attempt,
                    "worker_id": worker_id,
                })
        finally:
            task_queue.task_done()


def main():
    task_queue = PriorityQueue()
    cancel_event = {
        "task_ids": set(),
        "lock": Lock(),
    }
    results = []
    results_lock = Lock()

    tasks = [
        ScheduledTask(2, 1, "send-email", 0.004),
        ScheduledTask(1, 2, "write-invoice", 0.003, should_fail_once=True),
        ScheduledTask(3, 3, "refresh-cache", 0.002),
        ScheduledTask(0, 4, "record-payment", 0.001),
    ]

    for task in tasks:
        task_queue.put((task.priority, task.sequence, task))

    with cancel_event["lock"]:
        cancel_event["task_ids"].add("refresh-cache")

    workers = [
        Thread(
            target=scheduler_worker,
            args=(worker_id, task_queue, cancel_event, results, results_lock),
        )
        for worker_id in range(1, 3)
    ]

    for worker in workers:
        worker.start()

    task_queue.join()

    for stop_sequence in range(len(workers)):
        task_queue.put((99, stop_sequence, STOP_TASK))

    for worker in workers:
        worker.join()

    print("Priority Scheduler Cancellation")
    print("===============================")

    for result in sorted(results, key=lambda item: (item["task_id"], item["attempt"], item["status"])):
        print(
            "task={task_id} status={status} attempt={attempt}".format(
                **result
            )
        )

    print("completed={}".format(sum(1 for result in results if result["status"] == "done")))
    print("retries={}".format(sum(1 for result in results if result["status"] == "retry")))
    print("cancelled={}".format(sum(1 for result in results if result["status"] == "cancelled")))


if __name__ == "__main__":
    main()
