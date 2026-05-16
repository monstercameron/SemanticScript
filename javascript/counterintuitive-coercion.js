'use strict';

// JavaScript coercion examples that look wrong until the conversion rules are known.
const examples = [
  {
    expression: '[] == false',
    value: [] == false,
    reason: '[] becomes an empty string, then 0; false also becomes 0.',
  },
  {
    expression: '[] == ![]',
    value: [] == ![],
    reason: '![] is false, then the comparison follows the [] == false path.',
  },
  {
    expression: '"" == 0',
    value: '' == 0,
    reason: 'The empty string becomes numeric 0.',
  },
  {
    expression: '"0" == false',
    value: '0' == false,
    reason: 'Both sides become numeric 0.',
  },
  {
    expression: 'null == undefined',
    value: null == undefined,
    reason: 'Loose equality has a special case for null and undefined.',
  },
  {
    expression: 'null == 0',
    value: null == 0,
    reason: 'The null/undefined special case does not extend to numbers.',
  },
  {
    expression: 'Boolean("false")',
    value: Boolean('false'),
    reason: 'Any non-empty string is truthy.',
  },
];

console.log('Counterintuitive Coercion');
console.log('=========================');

examples.forEach((example) => {
  console.log(`${example.expression} => ${example.value}`);
  console.log(`  ${example.reason}`);
});
