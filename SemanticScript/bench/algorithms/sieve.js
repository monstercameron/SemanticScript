// sieve.js - Sieve of Eratosthenes up to LIMIT, repeated REPEATS times.
// Mirrors sieve.c: same LIMIT/REPEATS, same checksum, same output contract.
// Uses a Uint8Array (flat byte buffer) re-zeroed each repeat via the C-level
// fill(); the inner marking loop naturally stops at sqrt(LIMIT) because
// candidate*candidate exceeds LIMIT beyond that. Wrapped in main() so V8
// JIT-optimizes the hot loops.

function main() {
  const limit = 2000000;
  const repeats = 20;
  const arraySize = limit + 1;

  const sieve = new Uint8Array(arraySize);
  let totalPrimeCount = 0;

  const start = performance.now();
  for (let repeat = 0; repeat < repeats; repeat++) {
    sieve.fill(0);
    let primeCount = 0;
    for (let candidate = 2; candidate <= limit; candidate++) {
      if (sieve[candidate] === 0) {
        primeCount++;
        for (let multiple = candidate * candidate; multiple <= limit; multiple += candidate) {
          sieve[multiple] = 1;
        }
      }
    }
    totalPrimeCount += primeCount;
  }
  const end = performance.now();

  const elapsedSeconds = (end - start) / 1000;
  console.log(`checksum=${totalPrimeCount} elapsedSeconds=${elapsedSeconds.toFixed(6)}`);
}

main();
