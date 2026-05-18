'use strict';

// Lambda-calculus style Church encodings in plain JavaScript functions.
// This is intentionally alien-looking while still producing obvious output.
const TRUE = (thenValue) => () => thenValue;
const FALSE = () => (elseValue) => elseValue;

const IF = (condition) => (thenValue) => (elseValue) => condition(thenValue)(elseValue);

const ZERO = () => (value) => value;
const SUCC = (number) => (next) => (value) => next(number(next)(value));
const ADD = (left) => (right) => (next) => (value) => left(next)(right(next)(value));
const MULTIPLY = (left) => (right) => (next) => left(right(next));

const PAIR = (left) => (right) => (selector) => selector(left)(right);
const FIRST = (pair) => pair(TRUE);
const SECOND = (pair) => pair(FALSE);

const toNumber = (churchNumber) => churchNumber((value) => value + 1)(0);
const toBoolean = (churchBoolean) => IF(churchBoolean)('true')('false');

const ONE = SUCC(ZERO);
const TWO = SUCC(ONE);
const THREE = SUCC(TWO);
const FIVE = ADD(TWO)(THREE);
const SIX = MULTIPLY(TWO)(THREE);
const encodedPair = PAIR(FIVE)(SIX);

console.log('Esoteric Church Encoding');
console.log('========================');
console.log(`two: ${toNumber(TWO)}`);
console.log(`three: ${toNumber(THREE)}`);
console.log(`twoPlusThree: ${toNumber(FIVE)}`);
console.log(`twoTimesThree: ${toNumber(SIX)}`);
console.log(`first(pair): ${toNumber(FIRST(encodedPair))}`);
console.log(`second(pair): ${toNumber(SECOND(encodedPair))}`);
console.log(`ifTrue: ${toBoolean(TRUE)}`);
console.log(`ifFalse: ${toBoolean(FALSE)}`);
