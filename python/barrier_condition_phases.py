from threading import Barrier, Condition, Thread
import time


# Coordinates several workers through a Condition start gate and repeated
# Barrier phase joins. This models phased work such as startup, processing,
# and shutdown in a multithreaded service.
WORKER_COUNT = 4
PHASES = ["load", "process", "flush"]


class StartGate:
    def __init__(self):
        self.condition = Condition()
        self.open = False

    def wait_until_open(self):
        with self.condition:
            while not self.open:
                self.condition.wait()

    def open_gate(self):
        with self.condition:
            self.open = True
            self.condition.notify_all()


def worker(worker_id, start_gate, phase_barrier, audit_log):
    start_gate.wait_until_open()

    for phase_index, phase_name in enumerate(PHASES, start=1):
        time.sleep(0.002 * ((worker_id + phase_index) % 3))
        audit_log.append({
            "phase": phase_index,
            "worker_id": worker_id,
            "message": "worker={} phase={}".format(worker_id, phase_name),
        })
        phase_barrier.wait()


def main():
    start_gate = StartGate()
    phase_barrier = Barrier(WORKER_COUNT)
    audit_log = []

    threads = [
        Thread(target=worker, args=(worker_id, start_gate, phase_barrier, audit_log))
        for worker_id in range(1, WORKER_COUNT + 1)
    ]

    for thread in threads:
        thread.start()

    time.sleep(0.005)
    start_gate.open_gate()

    for thread in threads:
        thread.join()

    print("Barrier Condition Phases")
    print("========================")

    for entry in sorted(audit_log, key=lambda item: (item["phase"], item["worker_id"])):
        print(entry["message"])

    print("workers={}".format(WORKER_COUNT))
    print("phases={}".format(len(PHASES)))
    print("events={}".format(len(audit_log)))


if __name__ == "__main__":
    main()
