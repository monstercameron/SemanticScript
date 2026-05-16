'use strict';

// Deterministic calculator baseline with simple branching and formatted output.
const operations = [
  { name: 'add', left: 8, right: 4 },
  { name: 'subtract', left: 8, right: 4 },
  { name: 'multiply', left: 8, right: 4 },
  { name: 'divide', left: 8, right: 4 },
  { name: 'power', left: 2, right: 5 },
];

const padRight = (value, width) => {
  const text = String(value);
  return text + ' '.repeat(Math.max(width - text.length, 0));
};

const calculate = (operation) => {
  if (operation.name === 'add') {
    return operation.left + operation.right;
  }

  if (operation.name === 'subtract') {
    return operation.left - operation.right;
  }

  if (operation.name === 'multiply') {
    return operation.left * operation.right;
  }

  if (operation.name === 'divide') {
    return operation.left / operation.right;
  }

  if (operation.name === 'power') {
    return operation.left ** operation.right;
  }

  throw new Error(`Unsupported operation: ${operation.name}`);
};

console.log('Simple Calculator');
console.log('=================');

operations.forEach((operation) => {
  const result = calculate(operation);
  console.log(`${padRight(operation.name, 8)} ${operation.left} ${operation.right} => ${result}`);
});
