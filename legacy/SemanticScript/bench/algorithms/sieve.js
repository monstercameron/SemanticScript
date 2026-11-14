// sieve.js - Sieve of Eratosthenes up to LIMIT, repeated REPEATS times.
// Same structure as the other three languages: a Uint8Array starts all-prime
// (1), composites are struck out (0) for primes up to sqrt(LIMIT), and the
// prime count is a final pass. Wrapped in main() so V8 JIT-optimizes the
// hot loops. Same LIMIT/REPEATS, same checksum, same output contract.

function main() {
  const limit = 2000000;
  const repeats = 40;
  const arraySize = limit + 1;

  const sieve = new Uint8Array(arraySize);
  let totalPrimeCount = 0;

  const start = performance.now();
  for (let repeat = 0; repeat < repeats; repeat++) {
    sieve.fill(1);
    sieve[0] = 0;
    sieve[1] = 0;
    for (let candidate = 2; candidate * candidate <= limit; candidate++) {
      if (sieve[candidate]) {
        for (let multiple = candidate * candidate; multiple <= limit; multiple += candidate) {
          sieve[multiple] = 0;
        }
      }
    }
    let primeCount = 0;
    for (let index = 2; index <= limit; index++) {
      primeCount += sieve[index];
    }
    totalPrimeCount += primeCount;
  }
  const end = performance.now();

  const elapsedSeconds = (end - start) / 1000;
  console.log(`checksum=${totalPrimeCount} elapsedSeconds=${elapsedSeconds.toFixed(6)}`);
}

main();
