'use strict';

const EventEmitter = require('events');

// A deliberately complex baseline: checkout saga with idempotency, inventory
// reservations, retries, timeouts, compensation, an outbox, and event projections.
// It is deterministic, but the control flow is intentionally painful to trace.
const eventBus = new EventEmitter();

const inventoryBySku = {
  NOTEBOOK: { sku: 'NOTEBOOK', available: 4, reserved: 0, unitPriceCents: 499 },
  PEN: { sku: 'PEN', available: 20, reserved: 0, unitPriceCents: 129 },
  BAG: { sku: 'BAG', available: 1, reserved: 0, unitPriceCents: 2499 },
};

const ordersById = {};
const idempotencyPromisesByKey = {};
const paymentFailuresRemainingByOrder = {
  'order-1001': 1,
};

const outbox = [];
const traceLog = [];
const projection = {
  accepted: 0,
  reserved: 0,
  completed: 0,
  rejected: 0,
  compensated: 0,
};

const checkoutCommands = [
  {
    commandKey: 'cmd-1001',
    orderId: 'order-1001',
    customer: 'Ada',
    items: [
      { sku: 'NOTEBOOK', quantity: 2 },
      { sku: 'PEN', quantity: 3 },
    ],
    shippingDelayMilliseconds: 20,
  },
  {
    commandKey: 'cmd-1002',
    orderId: 'order-1002',
    customer: 'Grace',
    items: [
      { sku: 'BAG', quantity: 2 },
    ],
    shippingDelayMilliseconds: 10,
  },
  {
    commandKey: 'cmd-1003',
    orderId: 'order-1003',
    customer: 'Linus',
    items: [
      { sku: 'BAG', quantity: 1 },
      { sku: 'NOTEBOOK', quantity: 1 },
    ],
    shippingDelayMilliseconds: 60,
  },
  {
    commandKey: 'cmd-1004',
    orderId: 'order-1004',
    customer: 'Mallory',
    items: [
      { sku: 'PEN', quantity: 1 },
    ],
    shippingDelayMilliseconds: 15,
  },
  {
    // Same idempotency key as order-1001, so this must not reserve or charge twice.
    commandKey: 'cmd-1001',
    orderId: 'order-duplicate',
    customer: 'Ada',
    items: [
      { sku: 'NOTEBOOK', quantity: 2 },
    ],
    shippingDelayMilliseconds: 5,
  },
];

const delay = (milliseconds) => new Promise((resolve) => {
  setTimeout(resolve, milliseconds);
});

const formatMoney = (cents) => `$${(cents / 100).toFixed(2)}`;

const cloneItems = (items) => items.map((item) => ({
  sku: item.sku,
  quantity: item.quantity,
}));

const calculateOrderTotalCents = (items) => items.reduce((total, item) => {
  const inventoryItem = inventoryBySku[item.sku];
  return total + (inventoryItem.unitPriceCents * item.quantity);
}, 0);

const writeOutboxEvent = (eventType, payload) => {
  const event = {
    sequence: outbox.length + 1,
    eventType,
    payload,
  };

  outbox.push(event);
  eventBus.emit(eventType, event);
};

const recordTrace = (message) => {
  traceLog.push(message);
};

eventBus.on('order.accepted', (event) => {
  projection.accepted += 1;
  recordTrace(`accepted ${event.payload.orderId}`);
});

eventBus.on('inventory.reserved', (event) => {
  projection.reserved += 1;
  recordTrace(`reserved ${event.payload.orderId}`);
});

eventBus.on('order.completed', (event) => {
  projection.completed += 1;
  recordTrace(`completed ${event.payload.orderId}`);
});

eventBus.on('order.rejected', (event) => {
  projection.rejected += 1;
  recordTrace(`rejected ${event.payload.orderId} reason=${event.payload.reason}`);
});

eventBus.on('order.compensated', (event) => {
  projection.compensated += 1;
  recordTrace(`compensated ${event.payload.orderId} reason=${event.payload.reason}`);
});

const withTimeout = (label, promise, timeoutMilliseconds) => new Promise((resolve, reject) => {
  const timeoutHandle = setTimeout(() => {
    reject(new Error(`${label} timed out after ${timeoutMilliseconds}ms`));
  }, timeoutMilliseconds);

  promise.then((value) => {
    clearTimeout(timeoutHandle);
    resolve(value);
  }).catch((error) => {
    clearTimeout(timeoutHandle);
    reject(error);
  });
});

const retryPromise = (label, maximumAttempts, createAttemptPromise) => {
  const attempt = (attemptNumber) => createAttemptPromise(attemptNumber)
    .catch((error) => {
      recordTrace(`${label} attempt ${attemptNumber} failed: ${error.message}`);

      if (attemptNumber >= maximumAttempts) {
        throw error;
      }

      return delay(5).then(() => attempt(attemptNumber + 1));
    });

  return attempt(1);
};

const reserveInventory = (orderId, items) => {
  const reservations = [];

  for (let index = 0; index < items.length; index += 1) {
    const item = items[index];
    const inventoryItem = inventoryBySku[item.sku];

    if (!inventoryItem) {
      releaseReservations(reservations);
      return {
        ok: false,
        reason: `unknown sku ${item.sku}`,
        reservations: [],
      };
    }

    const remainingStock = inventoryItem.available - inventoryItem.reserved;

    if (remainingStock < item.quantity) {
      releaseReservations(reservations);
      return {
        ok: false,
        reason: `insufficient stock for ${item.sku}`,
        reservations: [],
      };
    }

    inventoryItem.reserved += item.quantity;
    reservations.push({
      orderId,
      sku: item.sku,
      quantity: item.quantity,
    });
  }

  return {
    ok: true,
    reason: null,
    reservations,
  };
};

const releaseReservations = (reservations) => {
  reservations.forEach((reservation) => {
    inventoryBySku[reservation.sku].reserved -= reservation.quantity;
  });
};

const commitReservations = (reservations) => {
  reservations.forEach((reservation) => {
    const inventoryItem = inventoryBySku[reservation.sku];
    inventoryItem.reserved -= reservation.quantity;
    inventoryItem.available -= reservation.quantity;
  });
};

const runFraudCheck = (order) => withTimeout(
  `fraudCheck ${order.id}`,
  delay(12).then(() => {
    if (order.customer === 'Mallory') {
      throw new Error('fraud review rejected customer');
    }

    return {
      score: order.customer === 'Ada' ? 7 : 12,
      decision: 'allow',
    };
  }),
  40
);

const authorizePayment = (order) => retryPromise(
  `payment ${order.id}`,
  3,
  (attemptNumber) => delay(10).then(() => {
    const failuresRemaining = paymentFailuresRemainingByOrder[order.id] || 0;

    if (failuresRemaining > 0) {
      paymentFailuresRemainingByOrder[order.id] = failuresRemaining - 1;
      throw new Error('transient gateway refusal');
    }

    return {
      authorizationId: `${order.id}-auth-${attemptNumber}`,
      amountCents: order.totalCents,
    };
  })
);

const quoteShipping = (order) => withTimeout(
  `shippingQuote ${order.id}`,
  delay(order.shippingDelayMilliseconds).then(() => ({
    quoteId: `${order.id}-ship-quote`,
    carrier: 'UPS',
    cents: order.items.length > 1 ? 799 : 499,
    fallback: false,
  })),
  35
).catch((error) => {
  recordTrace(`shipping fallback ${order.id}: ${error.message}`);

  return {
    quoteId: `${order.id}-manual-quote`,
    carrier: 'manual-review',
    cents: 0,
    fallback: true,
  };
});

const summarizeOrder = (order, duplicate) => ({
  orderId: order.id,
  customer: order.customer,
  status: order.status,
  totalCents: order.totalCents,
  duplicate: duplicate === true,
  failureReason: order.failureReason || '',
  shippingCarrier: order.shippingQuote ? order.shippingQuote.carrier : '',
});

const processCheckoutCommand = (command) => {
  if (idempotencyPromisesByKey[command.commandKey]) {
    return idempotencyPromisesByKey[command.commandKey].then((summary) => {
      recordTrace(`duplicate ${command.commandKey} reused ${summary.orderId}`);
      return Object.assign({}, summary, { duplicate: true });
    });
  }

  const processPromise = processNewCheckoutCommand(command);
  idempotencyPromisesByKey[command.commandKey] = processPromise;
  return processPromise;
};

const processNewCheckoutCommand = (command) => {
  const order = {
    id: command.orderId,
    customer: command.customer,
    items: cloneItems(command.items),
    totalCents: calculateOrderTotalCents(command.items),
    shippingDelayMilliseconds: command.shippingDelayMilliseconds,
    status: 'accepted',
    failureReason: '',
    paymentAuthorization: null,
    shippingQuote: null,
  };

  ordersById[order.id] = order;
  writeOutboxEvent('order.accepted', {
    orderId: order.id,
    customer: order.customer,
    totalCents: order.totalCents,
  });

  const reservationResult = reserveInventory(order.id, order.items);

  if (!reservationResult.ok) {
    order.status = 'rejected';
    order.failureReason = reservationResult.reason;
    writeOutboxEvent('order.rejected', {
      orderId: order.id,
      reason: reservationResult.reason,
    });
    return Promise.resolve(summarizeOrder(order, false));
  }

  writeOutboxEvent('inventory.reserved', {
    orderId: order.id,
    items: cloneItems(order.items),
  });

  return runFraudCheck(order)
    .then(() => authorizePayment(order))
    .then((authorization) => {
      order.paymentAuthorization = authorization;
      return quoteShipping(order);
    })
    .then((shippingQuote) => {
      order.shippingQuote = shippingQuote;
      commitReservations(reservationResult.reservations);
      order.status = 'completed';

      writeOutboxEvent('order.completed', {
        orderId: order.id,
        authorizationId: order.paymentAuthorization.authorizationId,
        shippingCarrier: shippingQuote.carrier,
      });

      return summarizeOrder(order, false);
    })
    .catch((error) => {
      releaseReservations(reservationResult.reservations);
      order.status = 'failed';
      order.failureReason = error.message;

      writeOutboxEvent('order.compensated', {
        orderId: order.id,
        reason: error.message,
      });

      return summarizeOrder(order, false);
    });
};

const printOrderSummaries = (summaries) => {
  console.log('Order Results');
  console.log('-------------');

  summaries.forEach((summary) => {
    const duplicateText = summary.duplicate ? ' duplicate=true' : '';
    const failureText = summary.failureReason ? ` failure="${summary.failureReason}"` : '';
    const carrierText = summary.shippingCarrier ? ` carrier=${summary.shippingCarrier}` : '';
    console.log(`${summary.orderId} status=${summary.status}${carrierText}${duplicateText}${failureText} total=${formatMoney(summary.totalCents)}`);
  });
};

const printInventory = () => {
  console.log('');
  console.log('Inventory');
  console.log('---------');

  Object.keys(inventoryBySku).sort().forEach((sku) => {
    const item = inventoryBySku[sku];
    console.log(`${sku} available=${item.available} reserved=${item.reserved}`);
  });
};

const printOutbox = () => {
  console.log('');
  console.log('Outbox');
  console.log('------');

  outbox.forEach((event) => {
    console.log(`${event.sequence}. ${event.eventType} ${event.payload.orderId}`);
  });
};

const printTrace = () => {
  console.log('');
  console.log('Trace');
  console.log('-----');

  traceLog.forEach((entry) => {
    console.log(entry);
  });
};

const printProjection = () => {
  console.log('');
  console.log('Projection');
  console.log('----------');
  console.log(`accepted=${projection.accepted}`);
  console.log(`reserved=${projection.reserved}`);
  console.log(`completed=${projection.completed}`);
  console.log(`rejected=${projection.rejected}`);
  console.log(`compensated=${projection.compensated}`);
};

console.log('Complex Checkout Saga');
console.log('=====================');

Promise.all(checkoutCommands.map(processCheckoutCommand))
  .then((summaries) => {
    printOrderSummaries(summaries);
    printInventory();
    printOutbox();
    printTrace();
    printProjection();
  })
  .catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
