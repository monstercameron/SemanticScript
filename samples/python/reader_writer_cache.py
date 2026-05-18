from threading import Condition, Lock, Thread
import time


# Reader/writer lock and cache example. Multiple readers can enter together,
# writers get exclusive access, and final output is sorted for deterministic logs.
class ReaderWriterLock:
    def __init__(self):
        self.condition = Condition()
        self.active_readers = 0
        self.writer_active = False

    def acquire_read(self):
        with self.condition:
            while self.writer_active:
                self.condition.wait()
            self.active_readers += 1

    def release_read(self):
        with self.condition:
            self.active_readers -= 1
            if self.active_readers == 0:
                self.condition.notify_all()

    def acquire_write(self):
        with self.condition:
            while self.writer_active or self.active_readers > 0:
                self.condition.wait()
            self.writer_active = True

    def release_write(self):
        with self.condition:
            self.writer_active = False
            self.condition.notify_all()


class SharedCache:
    def __init__(self):
        self.lock = ReaderWriterLock()
        self.values = {
            "feature.alpha": "enabled",
            "feature.beta": "disabled",
        }

    def read_value(self, key):
        self.lock.acquire_read()
        try:
            time.sleep(0.003)
            return self.values.get(key, "missing")
        finally:
            self.lock.release_read()

    def write_value(self, key, value):
        self.lock.acquire_write()
        try:
            time.sleep(0.004)
            self.values[key] = value
        finally:
            self.lock.release_write()


def run_operation(cache, operation, audit_log, audit_lock):
    time.sleep(operation["delay"])

    if operation["kind"] == "read":
        value = cache.read_value(operation["key"])
        with audit_lock:
            audit_log.append({
                "order": operation["order"],
                "message": "read {}={}".format(operation["key"], value),
            })
        return

    cache.write_value(operation["key"], operation["value"])
    with audit_lock:
        audit_log.append({
            "order": operation["order"],
            "message": "write {}={}".format(operation["key"], operation["value"]),
        })


def main():
    cache = SharedCache()
    audit_log = []
    audit_lock = Lock()

    operation_phases = [
        [
            {"order": 1, "kind": "read", "key": "feature.alpha", "delay": 0.000},
            {"order": 2, "kind": "read", "key": "feature.beta", "delay": 0.000},
        ],
        [
            {"order": 3, "kind": "write", "key": "feature.beta", "value": "enabled", "delay": 0.000},
        ],
        [
            {"order": 4, "kind": "read", "key": "feature.beta", "delay": 0.000},
        ],
        [
            {"order": 5, "kind": "write", "key": "feature.gamma", "value": "enabled", "delay": 0.000},
        ],
        [
            {"order": 6, "kind": "read", "key": "feature.gamma", "delay": 0.000},
        ],
    ]

    # Each phase may contain concurrent operations, but phases run in order so
    # benchmark output stays deterministic.
    for phase in operation_phases:
        threads = [
            Thread(target=run_operation, args=(cache, operation, audit_log, audit_lock))
            for operation in phase
        ]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

    print("Reader Writer Cache")
    print("===================")

    for entry in sorted(audit_log, key=lambda item: item["order"]):
        print("{order}. {message}".format(**entry))

    print("finalCache:")
    for key in sorted(cache.values):
        print("  {}={}".format(key, cache.values[key]))


if __name__ == "__main__":
    main()
