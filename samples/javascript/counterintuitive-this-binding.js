'use strict';

// Method calls, detached functions, and arrow functions all bind this differently.
const counter = {
  count: 3,
  readCount() {
    return this.count;
  },
  makeArrowReader() {
    return () => this.count;
  },
};

const detachedReadCount = counter.readCount;
const boundReadCount = counter.readCount.bind(counter);
const arrowReadCount = counter.makeArrowReader();

let detachedResult;

try {
  detachedResult = detachedReadCount();
} catch (error) {
  detachedResult = error.name;
}

const otherCounter = {
  count: 99,
  readCount: counter.readCount,
};

console.log('Counterintuitive This Binding');
console.log('=============================');
console.log(`counter.readCount() => ${counter.readCount()}`);
console.log(`detachedReadCount() => ${detachedResult}`);
console.log(`boundReadCount() => ${boundReadCount()}`);
console.log(`otherCounter.readCount() => ${otherCounter.readCount()}`);
console.log(`arrowReadCount.call({ count: 42 }) => ${arrowReadCount.call({ count: 42 })}`);
