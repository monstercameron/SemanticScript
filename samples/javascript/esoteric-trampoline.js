'use strict';

// Continuation-passing factorial evaluated by a trampoline instead of recursion.
// This is intentionally indirect: each step returns the next computation.
const done = (value) => ({
  done: true,
  value,
});

const call = (thunk) => ({
  done: false,
  thunk,
});

const trampoline = (nextStep) => {
  let currentStep = nextStep;
  let bounceCount = 0;

  while (!currentStep.done) {
    bounceCount += 1;
    currentStep = currentStep.thunk();
  }

  return {
    value: currentStep.value,
    bounceCount,
  };
};

const factorialContinuation = (number, continuation) => {
  if (number <= 1) {
    return call(() => continuation(1));
  }

  return call(() => factorialContinuation(number - 1, (partialResult) => (
    call(() => continuation(number * partialResult))
  )));
};

const runFactorial = (number) => trampoline(
  factorialContinuation(number, (result) => done(result))
);

const inputs = [3, 5, 8];

console.log('Esoteric Trampoline');
console.log('===================');

inputs.forEach((input) => {
  const result = runFactorial(input);
  console.log(`factorial(${input})=${result.value} bounces=${result.bounceCount}`);
});
