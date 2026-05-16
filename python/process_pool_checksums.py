from concurrent.futures import ProcessPoolExecutor
import hashlib


# CPU-style process pool example. Uses only standard library multiprocessing
# through ProcessPoolExecutor, with deterministic chunks and sorted output.
def checksum_chunk(chunk_id_and_text):
    chunk_id, text = chunk_id_and_text
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    vowel_count = sum(1 for character in text.lower() if character in "aeiou")

    return {
        "chunk_id": chunk_id,
        "length": len(text),
        "vowel_count": vowel_count,
        "digest_prefix": digest[:12],
    }


def main():
    chunks = [
        (1, "agents prefer explicit context"),
        (2, "threads need visible synchronization"),
        (3, "process pools avoid the gil for cpu work"),
        (4, "deterministic output makes benchmarks usable"),
    ]

    with ProcessPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(checksum_chunk, chunks))

    print("Process Pool Checksums")
    print("======================")

    for result in sorted(results, key=lambda item: item["chunk_id"]):
        print(
            "chunk={chunk_id} length={length} vowels={vowel_count} sha256={digest_prefix}".format(
                **result
            )
        )


if __name__ == "__main__":
    main()
