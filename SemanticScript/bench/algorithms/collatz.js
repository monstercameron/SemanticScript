// collatz.js - sum of Collatz stopping times for every start in 1..N.
// Mirrors collatz.c: same N, same checksum, same output contract.
// All intermediate Collatz values for N < 10^6 stay below 2^53, so plain
// JS numbers are exact here.

const n = 600000;
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
