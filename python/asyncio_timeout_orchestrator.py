import asyncio


# Async concurrency example with semaphore limits, per-call timeouts, retries,
# and deterministic result ordering.
SERVICE_CALLS = [
    {"name": "profile", "delay": 0.010, "timeout": 0.050, "failures": 0},
    {"name": "inventory", "delay": 0.020, "timeout": 0.050, "failures": 1},
    {"name": "pricing", "delay": 0.060, "timeout": 0.030, "failures": 0},
    {"name": "recommendations", "delay": 0.015, "timeout": 0.050, "failures": 0},
]


async def simulated_service_call(call, attempt):
    await asyncio.sleep(call["delay"])

    if attempt <= call["failures"]:
        raise RuntimeError("{} transient failure".format(call["name"]))

    return "{}-payload".format(call["name"])


async def call_with_retry(semaphore, call, maximum_attempts):
    attempts = []

    for attempt in range(1, maximum_attempts + 1):
        try:
            async with semaphore:
                result = await asyncio.wait_for(
                    simulated_service_call(call, attempt),
                    timeout=call["timeout"],
                )

            return {
                "name": call["name"],
                "status": "ok",
                "attempts": attempt,
                "result": result,
                "attemptLog": attempts,
            }
        except asyncio.TimeoutError:
            attempts.append("attempt {} timeout".format(attempt))
        except RuntimeError as error:
            attempts.append("attempt {} error {}".format(attempt, error))

    return {
        "name": call["name"],
        "status": "failed",
        "attempts": maximum_attempts,
        "result": "",
        "attemptLog": attempts,
    }


async def run_orchestrator():
    semaphore = asyncio.Semaphore(2)
    tasks = [
        asyncio.create_task(call_with_retry(semaphore, call, maximum_attempts=2))
        for call in SERVICE_CALLS
    ]

    results = await asyncio.gather(*tasks)
    return sorted(results, key=lambda item: item["name"])


def main():
    results = asyncio.run(run_orchestrator())

    print("Asyncio Timeout Orchestrator")
    print("===========================")

    for result in results:
        print(
            "service={name} status={status} attempts={attempts} result={result}".format(
                **result
            )
        )
        for attempt_message in result["attemptLog"]:
            print("  {}".format(attempt_message))


if __name__ == "__main__":
    main()
