'use strict';

// Numeric edge cases that commonly break simple assumptions.
const values = {
  decimalSum: 0.1 + 0.2,
  negativeZero: -0,
  largeInteger: 9007199254740992,
  largeIntegerPlusOne: 9007199254740992 + 1,
  notANumber: Number('not-a-number'),
};

console.log('Counterintuitive Numbers');
console.log('========================');
console.log(`0.1 + 0.2 => ${values.decimalSum}`);
console.log(`0.1 + 0.2 === 0.3 => ${values.decimalSum === 0.3}`);
console.log(`Object.is(-0, 0) => ${Object.is(values.negativeZero, 0)}`);
console.log(`1 / -0 => ${1 / values.negativeZero}`);
console.log(`9007199254740992 + 1 => ${values.largeIntegerPlusOne}`);
console.log(`largeInteger === largeIntegerPlusOne => ${values.largeInteger === values.largeIntegerPlusOne}`);
console.log(`NaN === NaN => ${values.notANumber === values.notANumber}`);
console.log(`Number.isNaN(NaN) => ${Number.isNaN(values.notANumber)}`);
