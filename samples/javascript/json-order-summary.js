'use strict';

// JSON transform baseline: parse, validate lightly, aggregate, and print stable output.
const ordersJson = JSON.stringify([
  {
    id: 'order-1001',
    customer: 'Ada',
    items: [
      { sku: 'NOTEBOOK', quantity: 2, unitPriceCents: 499 },
      { sku: 'PEN', quantity: 5, unitPriceCents: 129 },
    ],
  },
  {
    id: 'order-1002',
    customer: 'Grace',
    items: [
      { sku: 'BAG', quantity: 1, unitPriceCents: 2499 },
    ],
  },
  {
    id: 'order-1003',
    customer: 'Ada',
    items: [
      { sku: 'PEN', quantity: 2, unitPriceCents: 129 },
    ],
  },
]);

const calculateOrderTotalCents = (order) => order.items.reduce((total, item) => (
  total + (item.quantity * item.unitPriceCents)
), 0);

const summarizeOrders = (orders) => {
  const customerTotals = orders.reduce((totals, order) => {
    const orderTotalCents = calculateOrderTotalCents(order);
    totals[order.customer] = (totals[order.customer] || 0) + orderTotalCents;
    return totals;
  }, {});

  return {
    orderCount: orders.length,
    totalCents: orders.reduce((total, order) => total + calculateOrderTotalCents(order), 0),
    customerTotals,
    orderTotals: orders.map((order) => ({
      id: order.id,
      customer: order.customer,
      totalCents: calculateOrderTotalCents(order),
    })),
  };
};

const orders = JSON.parse(ordersJson);
const summary = summarizeOrders(orders);

console.log('JSON Order Summary');
console.log('==================');
console.log(JSON.stringify(summary, null, 2));
