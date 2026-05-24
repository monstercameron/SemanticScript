// collatz.js - sum of Collatz stopping times for every start in 1..N.
// Mirrors collatz.c: same N, same checksum, same output contract.
//
// Intermediate Collatz values for N < 10^6 reach ~10^11, which exceeds 2^31,
// so this MUST use arithmetic (% 2, / 2), not bitwise operators: JS bitwise
// ops coerce to 32-bit and would corrupt the values. Plain JS numbers are
// exact here because every value stays below 2^53. The hot loop is wrapped in
// main() so V8 JIT-optimizes it.

function main() {
  const n = 1000000;
  let totalSteps = 0;

  const start = performance.now();
  for (let k = 1; k <= n; k++) {
    let value = k;
    let steps = 0;
    while (value !== 1) {
      if (value % 2 === 0) {
        value = value / 2;
      } else {
        value = 3 * value + 1;
      }
      steps++;
    }
    totalSteps += steps;
  }
  const end = performance.now();

  const elapsedSeconds = (end - start) / 1000;
  console.log(`checksum=${totalSteps} elapsedSeconds=${elapsedSeconds.toFixed(6)}`);
}

main();
