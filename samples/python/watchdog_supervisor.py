from queue import Queue
from threading import Event, Lock, Thread
import time


# Supervisor/watchdog example. Worker heartbeats are monitored; a stalled worker
# is detected and replaced with a recovery worker.
STOP = object()


class Heartbeats:
    def __init__(self):
        self.lock = Lock()
        self.last_seen_by_worker = {}

    def mark(self, worker_name):
        with self.lock:
            self.last_seen_by_worker[worker_name] = time.monotonic()

    def snapshot(self):
        with self.lock:
            return dict(self.last_seen_by_worker)


def worker(worker_name, task_queue, heartbeat, audit_log, stop_event, stall_after_task=None):
    processed_count = 0

    while not stop_event.is_set():
        task = task_queue.get()

        try:
            if task is STOP:
                return

            heartbeat.mark(worker_name)
            time.sleep(task["duration"])
            processed_count += 1

            audit_log.append("{} processed {}".format(worker_name, task["task_id"]))

            if stall_after_task is not None and processed_count >= stall_after_task:
                audit_log.append("{} stalled".format(worker_name))
                time.sleep(0.050)
                return
        finally:
            task_queue.task_done()


def watchdog(heartbeat, audit_log, stop_event, stale_after_seconds):
    detected = set()

    while not stop_event.is_set():
        now = time.monotonic()
        snapshot = heartbeat.snapshot()

        for worker_name, last_seen in snapshot.items():
            if worker_name not in detected and now - last_seen > stale_after_seconds:
                detected.add(worker_name)
                audit_log.append("watchdog detected stale {}".format(worker_name))

        time.sleep(0.004)


def main():
    task_queue = Queue()
    heartbeat = Heartbeats()
    stop_event = Event()
    audit_log = []

    for task_id in range(1, 7):
        task_queue.put({
            "task_id": task_id,
            "duration": 0.004,
        })

    primary_worker = Thread(
        target=worker,
        args=("primary", task_queue, heartbeat, audit_log, stop_event, 2),
    )
    backup_worker = Thread(
        target=worker,
        args=("backup", task_queue, heartbeat, audit_log, stop_event, None),
    )
    watchdog_thread = Thread(
        target=watchdog,
        args=(heartbeat, audit_log, stop_event, 0.015),
    )

    primary_worker.start()
    backup_worker.start()
    watchdog_thread.start()

    task_queue.join()

    for _ in range(2):
        task_queue.put(STOP)

    primary_worker.join()
    backup_worker.join()
    stop_event.set()
    watchdog_thread.join()

    print("Watchdog Supervisor")
    print("===================")

    for entry in sorted(audit_log):
        print(entry)


if __name__ == "__main__":
    main()
