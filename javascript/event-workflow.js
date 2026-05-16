'use strict';

const EventEmitter = require('events');

// EventEmitter baseline with explicit event names and deterministic event payloads.
const eventBus = new EventEmitter();
const auditEntries = [];

eventBus.on('order.created', (order) => {
  auditEntries.push(`created ${order.id} for ${order.customer}`);
});

eventBus.on('order.paid', (payment) => {
  auditEntries.push(`paid ${payment.orderId} amount=${payment.amountCents}`);
});

eventBus.on('order.shipped', (shipment) => {
  auditEntries.push(`shipped ${shipment.orderId} carrier=${shipment.carrier}`);
});

const createOrder = (id, customer, amountCents) => {
  const order = { id, customer, amountCents };
  eventBus.emit('order.created', order);
  return order;
};

const payOrder = (order) => {
  const payment = { orderId: order.id, amountCents: order.amountCents };
  eventBus.emit('order.paid', payment);
  return payment;
};

const shipOrder = (order, carrier) => {
  const shipment = { orderId: order.id, carrier };
  eventBus.emit('order.shipped', shipment);
  return shipment;
};

const order = createOrder('order-2001', 'Katherine', 3499);
payOrder(order);
shipOrder(order, 'UPS');

console.log('Event Workflow');
console.log('==============');
auditEntries.forEach((entry) => {
  console.log(entry);
});
