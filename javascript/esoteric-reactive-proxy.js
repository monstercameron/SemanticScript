'use strict';

// A tiny reactive graph using Proxy and explicit subscriptions.
// Mutating state triggers recomputation through deliberately indirect wiring.
const subscribersByProperty = {};
const trace = [];

const subscribe = (propertyName, subscriberName, handler) => {
  subscribersByProperty[propertyName] = subscribersByProperty[propertyName] || [];
  subscribersByProperty[propertyName].push({
    subscriberName,
    handler,
  });
};

const notify = (propertyName, nextValue, previousValue, state) => {
  const subscribers = subscribersByProperty[propertyName] || [];

  subscribers.forEach((subscriber) => {
    trace.push(`${subscriber.subscriberName} observed ${propertyName}: ${previousValue} -> ${nextValue}`);
    subscriber.handler(nextValue, previousValue, state);
  });
};

const state = new Proxy({
  priceCents: 1200,
  quantity: 2,
  discountCents: 0,
  totalCents: 2400,
  status: 'ready',
}, {
  set(target, propertyName, nextValue) {
    const previousValue = target[propertyName];
    target[propertyName] = nextValue;

    if (previousValue !== nextValue) {
      notify(propertyName, nextValue, previousValue, target);
    }

    return true;
  },
});

const recomputeTotal = (nextValue, previousValue, currentState) => {
  const nextTotalCents = (currentState.priceCents * currentState.quantity) - currentState.discountCents;
  state.totalCents = nextTotalCents;
};

const recomputeStatus = (nextValue, previousValue, currentState) => {
  state.status = currentState.totalCents > 0 ? 'ready' : 'free';
};

subscribe('priceCents', 'totalCalculator', recomputeTotal);
subscribe('quantity', 'totalCalculator', recomputeTotal);
subscribe('discountCents', 'totalCalculator', recomputeTotal);
subscribe('totalCents', 'statusCalculator', recomputeStatus);

state.quantity = 3;
state.discountCents = 500;
state.priceCents = 999;

console.log('Esoteric Reactive Proxy');
console.log('=======================');
console.log(`priceCents=${state.priceCents}`);
console.log(`quantity=${state.quantity}`);
console.log(`discountCents=${state.discountCents}`);
console.log(`totalCents=${state.totalCents}`);
console.log(`status=${state.status}`);
console.log('trace:');
trace.forEach((entry) => {
  console.log(entry);
});
