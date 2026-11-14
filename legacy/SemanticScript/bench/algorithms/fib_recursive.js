// fib_recursive.js - naive recursive Fibonacci.
// Mirrors fib_recursive.c: same n, same checksum, same output contract.
// The recursive function is what gets hot, so V8 JIT-optimizes it; the driver
// is wrapped in main() so all timed code runs inside a function. Timed with
// performance.now() (sub-millisecond resolution).

function fib(n) {
  if (n < 2) {
    return n;
  }
  return fib(n - 1) + fib(n - 2);
}

function main() {
  const n = 39;
  const start = performance.now();
  const checksum = fib(n);
  const end = performance.now();
  const elapsedSeconds = (end - start) / 1000;
  console.log(`checksum=${checksum} elapsedSeconds=${elapsedSeconds.toFixed(6)}`);
}

main();
