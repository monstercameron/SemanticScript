'use strict';

// var captures one shared binding; let creates a fresh binding per loop iteration.
const varCallbacks = [];
const letCallbacks = [];

for (var varIndex = 0; varIndex < 3; varIndex += 1) {
  varCallbacks.push(() => varIndex);
}

for (let letIndex = 0; letIndex < 3; letIndex += 1) {
  letCallbacks.push(() => letIndex);
}

const makeCounter = () => {
  let count = 0;

  return () => {
    count += 1;
    return count;
  };
};

const sharedCounter = makeCounter();
const firstCounterAlias = sharedCounter;
const secondCounterAlias = sharedCounter;

console.log('Counterintuitive Closure Capture');
console.log('================================');
console.log(`var callbacks => ${varCallbacks.map((callback) => callback()).join(', ')}`);
console.log(`let callbacks => ${letCallbacks.map((callback) => callback()).join(', ')}`);
console.log(`firstCounterAlias() => ${firstCounterAlias()}`);
console.log(`secondCounterAlias() => ${secondCounterAlias()}`);
console.log(`firstCounterAlias() again => ${firstCounterAlias()}`);
