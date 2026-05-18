'use strict';

// Node event loop order: synchronous work, nextTick, promise jobs, then timers.
// The final setTimeout prints after every scheduled callback has had a chance to run.
const events = [];

const record = (name) => {
  events.push(name);
};

record('sync-start');

process.nextTick(() => {
  record('nextTick');
});

Promise.resolve()
  .then(() => {
    record('promise-then-1');
  })
  .then(() => {
    record('promise-then-2');
  });

setTimeout(() => {
  record('timeout-0');
}, 0);

record('sync-end');

setTimeout(() => {
  console.log('Counterintuitive Event Loop');
  console.log('===========================');
  events.forEach((eventName, index) => {
    console.log(`${index + 1}. ${eventName}`);
  });
}, 10);
