from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from queue import Queue
from threading import Event, Lock, Thread
import hashlib
import time


# Hybrid orchestration: parser threads feed CPU-bound process-pool work, while
# an aggregator thread consumes completed futures. This mixes three concurrency
# mechanisms in one deterministic console benchmark.
STOP = object()


def parse_document(document):
    time.sleep(0.003 * (document["document_id"] % 3))
    words = [
        word.strip(".,;:!?").lower()
        for word in document["text"].split()
        if word.strip(".,;:!?")
    ]
    return {
        "document_id": document["document_id"],
        "words": words,
    }


def score_words(parsed_document):
    joined_words = " ".join(parsed_document["words"])
    digest = hashlib.sha256(joined_words.encode("utf-8")).hexdigest()
    unique_words = sorted(set(parsed_document["words"]))
    score = sum(len(word) for word in unique_words)

    return {
        "document_id": parsed_document["document_id"],
        "word_count": len(parsed_document["words"]),
        "unique_count": len(unique_words),
        "score": score,
        "digest_prefix": digest[:10],
    }


def parser_worker(input_queue, parsed_queue, metrics, metrics_lock):
    while True:
        document = input_queue.get()

        try:
            if document is STOP:
                parsed_queue.put(STOP)
                return

            parsed = parse_document(document)
            parsed_queue.put(parsed)

            with metrics_lock:
                metrics["parsed"] += 1
        finally:
            input_queue.task_done()


def process_submitter(parsed_queue, process_pool, future_queue, parser_count):
    stopped_parsers = 0

    while stopped_parsers < parser_count:
        parsed = parsed_queue.get()

        try:
            if parsed is STOP:
                stopped_parsers += 1
                continue

            future_queue.put(process_pool.submit(score_words, parsed))
        finally:
            parsed_queue.task_done()

    future_queue.put(STOP)


def future_aggregator(future_queue, results, metrics, metrics_lock):
    pending_futures = []

    while True:
        future = future_queue.get()

        try:
            if future is STOP:
                break

            pending_futures.append(future)
        finally:
            future_queue.task_done()

    for completed_future in as_completed(pending_futures):
        result = completed_future.result()
        results.append(result)

        with metrics_lock:
            metrics["scored"] += 1


def run_orchestrator():
    documents = [
        {"document_id": 1, "text": "Agents need explicit context and stable names."},
        {"document_id": 2, "text": "Threads parse text while processes compute scores."},
        {"document_id": 3, "text": "Hybrid orchestration is powerful but difficult to debug."},
        {"document_id": 4, "text": "Deterministic summaries make concurrent systems reviewable."},
        {"document_id": 5, "text": "SemanticScript tries to make all hidden flow visible."},
    ]

    parser_count = 2
    input_queue = Queue()
    parsed_queue = Queue()
    future_queue = Queue()
    metrics = {"parsed": 0, "scored": 0}
    metrics_lock = Lock()
    results = []
    stop_event = Event()

    for document in documents:
        input_queue.put(document)

    for _ in range(parser_count):
        input_queue.put(STOP)

    with ProcessPoolExecutor(max_workers=2) as process_pool:
        parser_threads = [
            Thread(
                target=parser_worker,
                args=(input_queue, parsed_queue, metrics, metrics_lock),
                name="parser-{}".format(index),
            )
            for index in range(1, parser_count + 1)
        ]
        submitter_thread = Thread(
            target=process_submitter,
            args=(parsed_queue, process_pool, future_queue, parser_count),
            name="process-submitter",
        )
        aggregator_thread = Thread(
            target=future_aggregator,
            args=(future_queue, results, metrics, metrics_lock),
            name="future-aggregator",
        )

        for thread in parser_threads:
            thread.start()

        submitter_thread.start()
        aggregator_thread.start()

        input_queue.join()
        parsed_queue.join()
        future_queue.join()

        for thread in parser_threads:
            thread.join()

        submitter_thread.join()
        aggregator_thread.join()

    stop_event.set()
    return metrics, sorted(results, key=lambda item: item["document_id"])


def main():
    metrics, results = run_orchestrator()

    print("Hybrid Thread Process Orchestrator")
    print("==================================")

    for result in results:
        print(
            "doc={document_id} words={word_count} unique={unique_count} score={score} sha={digest_prefix}".format(
                **result
            )
        )

    print("metrics parsed={parsed} scored={scored}".format(**metrics))


if __name__ == "__main__":
    main()
