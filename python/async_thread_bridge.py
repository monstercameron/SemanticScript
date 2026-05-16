import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
import time


# Async tasks dispatch blocking work to a thread pool and return results through
# asyncio queues. This creates an explicit bridge between cooperative and
# preemptive concurrency.
def blocking_normalize_record(record, audit_log, audit_lock):
    time.sleep(0.004 * (record["record_id"] % 3))

    normalized_name = record["name"].strip().title()
    normalized_email = record["email"].strip().lower()

    with audit_lock:
        audit_log.append("normalized {}".format(record["record_id"]))

    return {
        "record_id": record["record_id"],
        "name": normalized_name,
        "email": normalized_email,
    }


async def producer(input_queue, records):
    for record in records:
        await input_queue.put(record)

    await input_queue.put(None)


async def normalizer(input_queue, output_queue, executor, audit_log, audit_lock):
    loop = asyncio.get_running_loop()

    while True:
        record = await input_queue.get()

        try:
            if record is None:
                await output_queue.put(None)
                return

            normalized = await loop.run_in_executor(
                executor,
                blocking_normalize_record,
                record,
                audit_log,
                audit_lock,
            )
            await output_queue.put(normalized)
        finally:
            input_queue.task_done()


async def consumer(output_queue):
    records = []

    while True:
        record = await output_queue.get()

        try:
            if record is None:
                return sorted(records, key=lambda item: item["record_id"])

            records.append(record)
        finally:
            output_queue.task_done()


async def run_bridge():
    records = [
        {"record_id": 1, "name": " ada ", "email": " ADA@EXAMPLE.COM "},
        {"record_id": 2, "name": "grace", "email": "Grace@Example.com"},
        {"record_id": 3, "name": "  linus", "email": "LINUS@example.COM"},
        {"record_id": 4, "name": "barbara", "email": "Barbara@Example.com"},
    ]

    input_queue = asyncio.Queue()
    output_queue = asyncio.Queue()
    audit_log = []
    audit_lock = Lock()

    with ThreadPoolExecutor(max_workers=2) as executor:
        producer_task = asyncio.create_task(producer(input_queue, records))
        normalizer_task = asyncio.create_task(
            normalizer(input_queue, output_queue, executor, audit_log, audit_lock)
        )
        consumer_task = asyncio.create_task(consumer(output_queue))

        await producer_task
        await input_queue.join()
        await normalizer_task
        await output_queue.join()
        normalized_records = await consumer_task

    return normalized_records, sorted(audit_log)


def main():
    normalized_records, audit_log = asyncio.run(run_bridge())

    print("Async Thread Bridge")
    print("===================")

    for record in normalized_records:
        print("record={record_id} name={name} email={email}".format(**record))

    print("audit:")
    for audit_entry in audit_log:
        print("  {}".format(audit_entry))


if __name__ == "__main__":
    main()
